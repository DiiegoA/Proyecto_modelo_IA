from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from app.agent.prediction_contract import (
    alias_payload,
    compute_missing_fields,
    extract_prediction_fields,
    validate_prediction_fields,
)


FULL_MESSAGE = """
Haz una prediccion con este JSON:
{
  "age": 39,
  "workclass": "Private",
  "fnlwgt": 77516,
  "education": "Bachelors",
  "education.num": 13,
  "marital.status": "Never-married",
  "occupation": "Adm-clerical",
  "relationship": "Not-in-family",
  "race": "White",
  "sex": "Male",
  "capital.gain": 2174,
  "capital.loss": 0,
  "hours.per.week": 40,
  "native.country": "United-States"
}
"""


def test_extract_prediction_fields_from_mixed_formats():
    message = """
    Quiero una prediccion.
    edad: 39;
    sexo: hombre;
    education.num=13;
    marital.status: Never-married
    """

    extracted = extract_prediction_fields(message)

    assert extracted["age"] == 39
    assert extracted["sex"] == "Male"
    assert extracted["education_num"] == 13
    assert extracted["marital_status"] == "Never-married"


def test_extract_prediction_fields_from_natural_language_profile():
    message = (
        "Quiero una prediccion de ingresos. Soy hombre, tengo 39 anos, mi workclass es Private, "
        "mi fnlwgt es 77516, estudie Bachelors, mi education.num es 13, mi estado civil es Never-married, "
        "trabajo como Adm-clerical, mi relacion es Not-in-family, mi raza es White, tuve una ganancia "
        "de capital de 2174, una perdida de capital de 0, trabajo 40 horas por semana y naci en United-States."
    )

    extracted = extract_prediction_fields(message)

    assert extracted["age"] == 39
    assert extracted["sex"] == "Male"
    assert extracted["education"] == "Bachelors"
    assert extracted["occupation"] == "Adm-clerical"
    assert extracted["capital_gain"] == 2174
    assert extracted["hours_per_week"] == 40
    assert extracted["native_country"] == "United-States"


def test_validate_prediction_fields_accepts_complete_payload():
    extracted = extract_prediction_fields(FULL_MESSAGE)

    is_complete, missing_fields, payload = validate_prediction_fields(extracted)

    assert is_complete is True
    assert missing_fields == []
    assert payload is not None
    assert alias_payload(payload)["education.num"] == 13
    assert alias_payload(payload)["hours.per.week"] == 40
    assert alias_payload(payload)["workclass"] == "Private"
    assert alias_payload(payload)["native.country"] == "United-States"


def test_validate_prediction_fields_accepts_complete_natural_language_payload():
    message = (
        "Quiero una prediccion de ingresos. Soy hombre, tengo 39 anos, mi workclass es Private, "
        "mi fnlwgt es 77516, estudie Bachelors, mi education.num es 13, mi estado civil es Never-married, "
        "trabajo como Adm-clerical, mi relacion es Not-in-family, mi raza es White, tuve una ganancia "
        "de capital de 2174, una perdida de capital de 0, trabajo 40 horas por semana y naci en United-States."
    )

    extracted = extract_prediction_fields(message)
    is_complete, missing_fields, payload = validate_prediction_fields(extracted)

    assert is_complete is True
    assert missing_fields == []
    assert payload is not None
    assert alias_payload(payload)["capital.gain"] == 2174
    assert alias_payload(payload)["capital.loss"] == 0


def test_validate_prediction_fields_reports_missing_fields():
    extracted = {"age": 39, "sex": "Male", "workclass": "Private"}

    is_complete, missing_fields, payload = validate_prediction_fields(extracted)

    assert is_complete is False
    assert payload is None
    assert "fnlwgt" in missing_fields
    assert "native_country" in missing_fields
    assert compute_missing_fields(extracted) == missing_fields


@given(st.integers(min_value=17, max_value=100))
def test_extract_prediction_fields_keeps_numeric_ranges(age: int):
    extracted = extract_prediction_fields(f"edad: {age}")

    assert extracted["age"] == age
