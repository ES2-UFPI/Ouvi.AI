"""Testes das funções de segurança (hash de senha e JWT) e das configurações. Não usam banco."""
import base64
import json
from datetime import timedelta

import pytest

from app.core import security
from app.core.config import Settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


# ---------- senha ----------

def test_hash_e_verificacao_da_senha():
    hash_ = hash_password("Senha1234")
    assert hash_.startswith("$argon2")
    assert verify_password("Senha1234", hash_)
    assert not verify_password("outra-senha", hash_)


def test_o_mesmo_texto_gera_hashes_diferentes_por_causa_do_salt():
    assert hash_password("Senha1234") != hash_password("Senha1234")


# ---------- JWT ----------

def test_access_token_devolve_o_id_do_usuario():
    assert decode_token(create_access_token(42), expected_type="access") == 42


def test_refresh_token_devolve_o_id_do_usuario():
    assert decode_token(create_refresh_token(7), expected_type="refresh") == 7


def test_tipo_de_token_errado_e_recusado():
    with pytest.raises(InvalidTokenError):
        decode_token(create_refresh_token(1), expected_type="access")
    with pytest.raises(InvalidTokenError):
        decode_token(create_access_token(1), expected_type="refresh")


def test_token_com_texto_qualquer_e_recusado():
    with pytest.raises(InvalidTokenError):
        decode_token("nao-e-um-jwt", expected_type="access")


def test_token_assinado_com_outro_segredo_e_recusado(monkeypatch):
    token = create_access_token(1)
    monkeypatch.setattr(security, "get_settings", lambda: Settings(jwt_secret="outro-segredo"))
    with pytest.raises(InvalidTokenError):
        decode_token(token, expected_type="access")


def test_token_expirado_e_recusado(monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: Settings(access_token_expire_minutes=-1))
    with pytest.raises(InvalidTokenError):
        decode_token(create_access_token(1), expected_type="access")


def test_token_sem_assinatura_algoritmo_none_e_recusado():
    def parte(dados: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(dados).encode()).rstrip(b"=").decode()

    falso = f"{parte({'alg': 'none', 'typ': 'JWT'})}.{parte({'sub': '1', 'type': 'access'})}."
    with pytest.raises(InvalidTokenError):
        decode_token(falso, expected_type="access")


def test_validade_do_access_token_e_menor_que_a_do_refresh():
    from jose import jwt

    segredo = Settings().jwt_secret
    acesso = jwt.decode(create_access_token(1), segredo, algorithms=["HS256"])
    renovacao = jwt.decode(create_refresh_token(1), segredo, algorithms=["HS256"])
    assert timedelta(seconds=renovacao["exp"] - renovacao["iat"]) > timedelta(seconds=acesso["exp"] - acesso["iat"])


# ---------- configurações ----------

def test_origens_do_cors_separadas_por_virgula_sem_espacos_nem_vazios():
    settings = Settings(cors_origins="http://localhost:5173, https://ouvi.ai ,,")
    assert settings.cors_origins_list == ["http://localhost:5173", "https://ouvi.ai"]


def test_url_do_banco_sem_driver_usa_psycopg2():
    settings = Settings(database_url="postgresql://u:p@db:5432/x")
    assert settings.database_url == "postgresql+psycopg2://u:p@db:5432/x"


def test_url_do_banco_com_driver_nao_e_alterada():
    url = "postgresql+psycopg2://u:p@db:5432/x"
    assert Settings(database_url=url).database_url == url
