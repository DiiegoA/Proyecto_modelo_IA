import logging
import re
import time
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("api_logger")

_COLUMN_SANITIZER = re.compile(r"[^a-z0-9_]")
_MULTI_UNDERSCORE = re.compile(r"_+")
_MASK_PATTERN = re.compile(r"(?i)^(unknown|n/?a|null|nan|missing|none|-1|)$|^[^a-zA-Z0-9]+$")
_LLM_OPERATORS = {"_+_": "+", "_-_": "-", "_*_": "*"}
_RARE_LABEL = "Rare"


class PipelineProduccionMLOps:
    """
    Standalone production pipeline compatible with the notebook artifact.

    The current notebook exports a partially broken pickle: several feature
    engineering recipes are not serialized, and the API receives raw JSON with
    snake_case / dotted-name mismatches. This class heals that gap at runtime.
    """

    def __init__(self, rutas: Dict, artefactos: Dict, modelos: Dict):
        self.rutas = rutas or {}
        self.artefactos = artefactos or {}
        self.modelos = modelos or {}
        self.umbral_oro = float(
            self.artefactos.get(
                "umbral_decision",
                self.rutas.get("umbral_decision_optimo", 0.50),
            )
        )
        self.version = "1.0.0"
        self.fecha_ensamblaje = time.strftime("%Y-%m-%d %H:%M:%S")

    def _ensure_runtime_state(self) -> None:
        if not hasattr(self, "rutas") or self.rutas is None:
            self.rutas = {}
        if not hasattr(self, "artefactos") or self.artefactos is None:
            self.artefactos = {}
        if not hasattr(self, "modelos") or self.modelos is None:
            self.modelos = {}
        if not hasattr(self, "umbral_oro"):
            self.umbral_oro = float(
                self.artefactos.get(
                    "umbral_decision",
                    self.rutas.get("umbral_decision_optimo", 0.50),
                )
            )
        if not hasattr(self, "_reference_dataset"):
            self._reference_dataset = None
        if not hasattr(self, "_did_infer_missing_artefacts"):
            self._did_infer_missing_artefacts = False

    def _get_modelo_final(self) -> Any:
        self._ensure_runtime_state()
        return self.modelos.get("oraculo_calibrado", self.modelos.get("oraculo_lightgbm"))

    def _get_training_feature_names(self) -> list[str]:
        modelo_final = self._get_modelo_final()
        if modelo_final is None:
            return []

        if hasattr(modelo_final, "feature_names_in_"):
            return [str(col) for col in modelo_final.feature_names_in_]

        if hasattr(modelo_final, "estimator") and hasattr(modelo_final.estimator, "feature_name_"):
            feature_names = modelo_final.estimator.feature_name_
            feature_names = feature_names() if callable(feature_names) else feature_names
            return [str(col) for col in feature_names]

        if hasattr(modelo_final, "booster_"):
            return [str(col) for col in modelo_final.booster_.feature_name()]

        return []

    @staticmethod
    def _sanitize_column_name(name: Any) -> str:
        text = str(name).strip().lower()
        text = _COLUMN_SANITIZER.sub("_", text)
        text = _MULTI_UNDERSCORE.sub("_", text)
        return text.strip("_")

    @classmethod
    def _sanitize_text_series(cls, series: pd.Series) -> pd.Series:
        mask = series.isna()
        clean = series.astype("string")
        clean = clean.str.lower()
        clean = clean.str.normalize("NFKD").str.encode("ascii", errors="ignore").str.decode("utf-8")
        clean = clean.str.replace(r"\s+", " ", regex=True)
        clean = clean.str.replace(r"\s*([^\w\s])\s*", r"\1", regex=True)
        clean = clean.str.replace(r"(?<=\d)\s+(?=[a-z])|(?<=[a-z])\s+(?=\d)", "", regex=True)
        clean = clean.str.strip().str.replace(r"\s+", "_", regex=True)
        clean = clean.astype(object)
        clean[mask] = np.nan
        return clean

    @classmethod
    def _normalize_input_frame(cls, X_raw: pd.DataFrame) -> pd.DataFrame:
        X = X_raw.copy()
        X.columns = [cls._sanitize_column_name(col) for col in X.columns]

        for col in X.columns:
            dtype = X[col].dtype
            if (
                pd.api.types.is_object_dtype(dtype)
                or pd.api.types.is_string_dtype(dtype)
                or isinstance(dtype, pd.CategoricalDtype)
            ):
                X[col] = cls._sanitize_text_series(X[col])
        return X

    def _reference_dataset_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "adult.csv"

    def _load_reference_dataset(self) -> Optional[pd.DataFrame]:
        self._ensure_runtime_state()
        if self._reference_dataset is not None:
            return self._reference_dataset.copy()

        dataset_path = self._reference_dataset_path()
        if not dataset_path.exists():
            logger.warning(
                "No se encontro '%s'; la inferencia seguira sin reconstruir recetas faltantes.",
                dataset_path,
            )
            return None

        try:
            df = pd.read_csv(dataset_path, sep=";")
        except Exception as exc:
            logger.warning(
                "No fue posible leer '%s' para reconstruir artefactos de inferencia: %s",
                dataset_path,
                exc,
            )
            return None

        df = self._normalize_input_frame(df)
        self._reference_dataset = df
        return df.copy()

    def _get_rare_recipe(self) -> Dict[str, list]:
        self._ensure_runtime_state()
        recipe = self.artefactos.get("receta_categorias_raras")
        if recipe:
            return recipe
        recipe = self.modelos.get("vocabulario_rare_labeling")
        if recipe:
            return recipe
        return {}

    def _get_binary_recipe(self) -> Dict[str, Dict[Any, int]]:
        self._ensure_runtime_state()
        recipe = self.artefactos.get("receta_mapeo_binario") or self.artefactos.get("reglas_binarias") or {}
        return {
            col: mapping
            for col, mapping in recipe.items()
            if not str(col).startswith("TARGET_")
        }

    def _get_target_recipe(self) -> Dict[str, Dict[str, Dict[Any, float]]]:
        self._ensure_runtime_state()
        return self.artefactos.get("receta_target_encoding") or self.artefactos.get("receta_woe_encoding") or {}

    def _get_ratio_recipe(self) -> Iterable[tuple]:
        self._ensure_runtime_state()
        return self.artefactos.get("receta_ratios_matematicos") or self.artefactos.get("receta_ratios_train") or []

    def _get_llm_recipe(self) -> Dict[str, str]:
        self._ensure_runtime_state()
        return self.artefactos.get("receta_llm_fe") or {}

    def _learn_rare_recipe(self, X: pd.DataFrame, threshold: float = 0.01) -> Dict[str, list]:
        recipe: Dict[str, list] = {}
        cat_cols = X.select_dtypes(include=["object", "category", "string"]).columns.tolist()

        for col in cat_cols:
            frequencies = X[col].value_counts(normalize=True)
            valid_categories = frequencies[frequencies >= threshold].index.tolist()
            masks = [val for val in frequencies.index if _MASK_PATTERN.match(str(val).strip())]
            valid_categories.extend(masks)
            valid_categories = list(dict.fromkeys(valid_categories))
            rare_categories = frequencies[~frequencies.index.isin(valid_categories)]
            if not rare_categories.empty:
                recipe[col] = valid_categories

        return recipe

    @staticmethod
    def _apply_rare_labeling(X: pd.DataFrame, recipe: Dict[str, list]) -> pd.DataFrame:
        X_trans = X.copy()
        for col, valid_categories in recipe.items():
            if col not in X_trans.columns:
                continue
            mask_null = X_trans[col].isna()
            mask_replace = ~X_trans[col].isin(valid_categories) & ~mask_null
            X_trans.loc[mask_replace, col] = _RARE_LABEL
        return X_trans

    @staticmethod
    def _encode_binary_target(target: pd.Series) -> pd.Series:
        ordered_values = sorted(target.dropna().unique().tolist())
        mapping = {value: index for index, value in enumerate(ordered_values)}
        return target.map(mapping).astype(float)

    @staticmethod
    def _learn_binary_recipe(X: pd.DataFrame) -> Dict[str, Dict[Any, int]]:
        recipe: Dict[str, Dict[Any, int]] = {}
        for col in X.columns:
            values = X[col].dropna().unique().tolist()
            if len(values) != 2:
                continue
            if pd.api.types.is_numeric_dtype(X[col]):
                continue
            ordered_values = sorted(values)
            recipe[col] = {ordered_values[0]: 0, ordered_values[1]: 1}
        return recipe

    @staticmethod
    def _learn_target_encoding_recipe(
        X: pd.DataFrame,
        y: pd.Series,
        rutas: Optional[Dict[str, list]] = None,
        smoothing: float = 10.0,
    ) -> Dict[str, Dict[str, Dict[Any, float]]]:
        rutas = rutas or {"cat_vars": []}
        recipe: Dict[str, Dict[str, Dict[Any, float]]] = {}

        for col in X.columns:
            if col.startswith("TARGET_"):
                continue

            unique_values = X[col].dropna().nunique()
            is_numeric = pd.api.types.is_numeric_dtype(X[col])
            is_categorical = (
                col in rutas.get("cat_vars", [])
                or pd.api.types.is_object_dtype(X[col])
                or isinstance(X[col].dtype, pd.CategoricalDtype)
            )

            if not is_categorical or is_numeric or unique_values <= 2:
                continue

            working = X[col].astype(object)
            stats = pd.DataFrame({"Target": y, "Categoria": working}).groupby("Categoria")["Target"].agg(["count", "mean"])
            n_obs = stats["count"]
            global_mean = float(y.mean())
            smooth = (n_obs * stats["mean"] + smoothing * global_mean) / (n_obs + smoothing)
            recipe[col] = {
                "Target_Directo": {
                    **smooth.to_dict(),
                    "__GLOBAL_MEAN__": global_mean,
                }
            }

        return recipe

    def _infer_llm_recipe_from_feature_names(self, feature_names: Iterable[str]) -> Dict[str, str]:
        llm_recipe: Dict[str, str] = {}

        for feature_name in feature_names:
            if not feature_name.startswith("llm_"):
                continue

            expression = feature_name[4:]
            for token, operator in _LLM_OPERATORS.items():
                if token not in expression:
                    continue
                left, right = expression.split(token, 1)
                llm_recipe[feature_name] = f"X['{left}'] {operator} X['{right}']"
                break

        return llm_recipe

    def _infer_missing_artefacts(self) -> None:
        self._ensure_runtime_state()
        if self._did_infer_missing_artefacts:
            return

        feature_names = self._get_training_feature_names()
        needs_binary = "sex" in feature_names and not self._get_binary_recipe()
        needs_target = any(
            feature in feature_names
            for feature in ("workclass", "marital_status", "occupation", "relationship", "race", "native_country")
        ) and not self._get_target_recipe()
        needs_rare = (needs_binary or needs_target) and not self._get_rare_recipe()
        needs_llm = any(feature.startswith("llm_") for feature in feature_names) and not self._get_llm_recipe()

        if not any((needs_binary, needs_target, needs_rare, needs_llm)):
            self._did_infer_missing_artefacts = True
            return

        reference_df = self._load_reference_dataset()
        if reference_df is None:
            self._did_infer_missing_artefacts = True
            return

        target_name = self.rutas.get("target_name", "income")
        if target_name not in reference_df.columns:
            logger.warning(
                "El dataset de referencia no contiene la columna target '%s'; no se pudieron reconstruir todas las recetas.",
                target_name,
            )
            self._did_infer_missing_artefacts = True
            return

        X_ref = reference_df.drop(columns=[target_name]).copy()
        y_ref = self._encode_binary_target(reference_df[target_name].copy())

        rare_recipe = self._get_rare_recipe() or self._learn_rare_recipe(X_ref)
        X_rare = self._apply_rare_labeling(X_ref, rare_recipe)

        if rare_recipe and "receta_categorias_raras" not in self.artefactos:
            self.artefactos["receta_categorias_raras"] = rare_recipe

        binary_recipe = self._get_binary_recipe() or self._learn_binary_recipe(X_rare)
        if binary_recipe and "receta_mapeo_binario" not in self.artefactos:
            self.artefactos["receta_mapeo_binario"] = binary_recipe

        target_recipe = self._get_target_recipe() or self._learn_target_encoding_recipe(X_rare, y_ref, self.rutas)
        if target_recipe and "receta_target_encoding" not in self.artefactos and "receta_woe_encoding" not in self.artefactos:
            self.artefactos["receta_target_encoding"] = target_recipe

        llm_recipe = self._get_llm_recipe() or self._infer_llm_recipe_from_feature_names(feature_names)
        if llm_recipe and "receta_llm_fe" not in self.artefactos:
            self.artefactos["receta_llm_fe"] = llm_recipe

        if needs_binary or needs_target or needs_rare or needs_llm:
            logger.warning(
                "Se reconstruyeron artefactos faltantes del notebook usando '%s'. "
                "La causa raiz es un desajuste entre la exportacion del .pkl y la API.",
                self._reference_dataset_path().name,
            )

        self._did_infer_missing_artefacts = True

    def _apply_llm_formulas(self, X: pd.DataFrame) -> pd.DataFrame:
        llm_recipe = self._get_llm_recipe()
        if not llm_recipe:
            return X

        X_trans = X.copy()
        safe_env = {"np": np, "X": X_trans}

        for feature_name, formula in llm_recipe.items():
            try:
                X_trans[feature_name] = eval(formula, {"__builtins__": {}}, safe_env)
            except Exception:
                X_trans[feature_name] = 0.0

        return X_trans

    def _transformar_features(self, X_raw: pd.DataFrame) -> pd.DataFrame:
        self._ensure_runtime_state()
        self._infer_missing_artefacts()

        X = self._normalize_input_frame(X_raw)
        X = self._apply_llm_formulas(X)

        receta_raras = self._get_rare_recipe()
        if receta_raras:
            X = self._apply_rare_labeling(X, receta_raras)

        receta_target = self._get_target_recipe()
        for col, config_encoding in receta_target.items():
            if col not in X.columns:
                continue

            if "__GLOBAL_NEUTRAL__" in config_encoding:
                neutral = config_encoding.get("__GLOBAL_NEUTRAL__", 0.0)
                mask_nan = X[col].isna()
                pure_map = {key: value for key, value in config_encoding.items() if key != "__GLOBAL_NEUTRAL__"}
                X[col] = X[col].astype(object).map(pure_map).fillna(neutral)
                X.loc[mask_nan, col] = np.nan
                continue

            for class_name, mapping in config_encoding.items():
                global_mean = mapping.get("__GLOBAL_MEAN__", 0.0)
                pure_map = {key: value for key, value in mapping.items() if key != "__GLOBAL_MEAN__"}
                new_col = col if len(config_encoding) == 1 else f"{col}_prob_{class_name}"
                mask_nan = X[col].isna()
                X[new_col] = X[col].astype(object).map(pure_map).fillna(global_mean)
                X.loc[mask_nan, new_col] = np.nan

            if len(config_encoding) > 1:
                X.drop(columns=[col], inplace=True)

        receta_binaria = self._get_binary_recipe()
        for col, mapping in receta_binaria.items():
            if col in X.columns:
                X[col] = X[col].map(mapping).fillna(0).astype(int)

        receta_ratios = self._get_ratio_recipe()
        for ratio in receta_ratios:
            if len(ratio) != 3:
                continue
            if ratio[0] in X.columns and ratio[1] in X.columns and ratio[2] not in X.columns:
                div_col, num_col, ratio_name = ratio
            else:
                ratio_name, num_col, div_col = ratio

            if num_col in X.columns and div_col in X.columns:
                X[ratio_name] = X[num_col].astype(float) / (X[div_col].astype(float) + 1e-9)

        receta_winsor = self.artefactos.get("receta_winsorizacion", {})
        for col, (lim_inf, lim_sup) in receta_winsor.items():
            if col in X.columns:
                X[col] = pd.to_numeric(X[col], errors="coerce").clip(lower=lim_inf, upper=lim_sup)

        escalador = self.modelos.get("escalador_numerico")
        if escalador is not None:
            cols_to_scale = getattr(escalador, "feature_names_in_", [])
            cols_present = [col for col in cols_to_scale if col in X.columns]
            if cols_present:
                X.loc[:, cols_present] = escalador.transform(X[cols_present]).astype(np.float32)

        basura = (
            self.rutas.get("basura_boruta", [])
            + self.rutas.get("gemelos_colineales", [])
            + self.rutas.get("fugas_del_futuro", [])
        )
        basura_presente = [col for col in basura if col in X.columns]
        if basura_presente:
            X.drop(columns=basura_presente, inplace=True)

        return X

    def _coerce_model_input(self, X: pd.DataFrame, expected_features: list[str]) -> pd.DataFrame:
        X_final = X.copy()

        for feature in expected_features:
            if feature not in X_final.columns:
                X_final[feature] = np.nan

        X_final = X_final[expected_features].copy()

        receta_nativas = self.artefactos.get("receta_categorias_nativas", {})
        for col, categories in receta_nativas.items():
            if col in X_final.columns:
                dtype = pd.CategoricalDtype(categories=categories, ordered=False)
                X_final[col] = X_final[col].astype(str).replace("nan", np.nan).astype(dtype)

        for col in X_final.columns:
            if isinstance(X_final[col].dtype, pd.CategoricalDtype):
                continue
            if pd.api.types.is_object_dtype(X_final[col]) or pd.api.types.is_string_dtype(X_final[col]):
                X_final[col] = pd.to_numeric(X_final[col], errors="coerce")

        return X_final

    def predict_proba(self, X_raw: pd.DataFrame) -> np.ndarray:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            modelo_final = self._get_modelo_final()
            if modelo_final is None:
                raise RuntimeError("No hay un modelo cargado dentro del pipeline de produccion.")

            expected_features = self._get_training_feature_names()
            X_procesado = self._transformar_features(X_raw)
            X_final = self._coerce_model_input(X_procesado, expected_features or list(X_procesado.columns))
            return modelo_final.predict_proba(X_final)

    def predict(self, X_raw: pd.DataFrame) -> np.ndarray:
        probas = self.predict_proba(X_raw)

        if probas.shape[1] == 2:
            classes = (probas[:, 1] >= self.umbral_oro).astype(int)
            label_map = {0: "<=50K", 1: ">50K"}
            return np.array([label_map[value] for value in classes])

        return np.argmax(probas, axis=1)
