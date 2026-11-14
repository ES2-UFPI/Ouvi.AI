"""Testes da conta e do acesso (US02): cadastro, login, renovação do token e rotas protegidas.

Rodam contra a API inteira e o banco de teste (transação desfeita no final), com tokens reais.
"""
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, create_refresh_token
from app.modules.users.models import User

PASSWORD = "Senha1234"


def cadastrar(api, email="ana@teste.com", name="Ana", password=PASSWORD):
    return api.post("/auth/register", json={"name": name, "email": email, "password": password})


def entrar(api, email="ana@teste.com", password=PASSWORD):
    return api.post("/auth/login", json={"email": email, "password": password})


# ---------- cadastro ----------

def test_cadastro_devolve_201_sem_expor_a_senha(api):
    resposta = cadastrar(api)
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["name"] == "Ana" and corpo["email"] == "ana@teste.com" and "id" in corpo
    assert "password" not in corpo and "password_hash" not in corpo


def test_senha_e_guardada_com_hash_argon2_e_nunca_em_texto(api, db_session):
    cadastrar(api)
    usuario = db_session.scalar(select(User).where(User.email == "ana@teste.com"))
    assert usuario.password_hash.startswith("$argon2")
    assert PASSWORD not in usuario.password_hash


def test_email_e_guardado_em_minusculas_e_o_nome_sem_espacos_nas_pontas(api, db_session):
    cadastrar(api, email="Ana@Teste.COM", name="  Ana Maria  ")
    usuario = db_session.scalar(select(User).where(User.email == "ana@teste.com"))
    assert usuario is not None and usuario.name == "Ana Maria"


def test_email_repetido_responde_409_mesmo_com_outra_caixa(api):
    assert cadastrar(api).status_code == 201
    repetido = cadastrar(api, email="ANA@teste.com")
    assert repetido.status_code == 409
    assert repetido.json()["detail"] == "E-mail já cadastrado"


@pytest.mark.parametrize("email", ["sem-arroba", "ana@", "@teste.com", ""])
def test_email_invalido_responde_422(api, email):
    assert cadastrar(api, email=email).status_code == 422


def test_senha_com_menos_de_8_caracteres_responde_422(api):
    assert cadastrar(api, password="1234567").status_code == 422


def test_senha_com_exatamente_8_caracteres_e_aceita(api):
    assert cadastrar(api, password="12345678").status_code == 201


@pytest.mark.parametrize("nome", ["", "   "])
def test_nome_vazio_ou_so_com_espacos_responde_422(api, nome):
    assert cadastrar(api, name=nome).status_code == 422


def test_cadastro_sem_campos_obrigatorios_responde_422(api):
    assert api.post("/auth/register", json={"email": "ana@teste.com"}).status_code == 422


# ---------- login ----------

def test_login_com_credenciais_corretas_devolve_os_dois_tokens(api):
    cadastrar(api)
    resposta = entrar(api)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["token_type"] == "bearer"
    assert corpo["access_token"] and corpo["refresh_token"]
    assert corpo["access_token"] != corpo["refresh_token"]


def test_login_aceita_o_email_em_outra_caixa(api):
    cadastrar(api)
    assert entrar(api, email="ANA@Teste.com").status_code == 200


def test_senha_errada_responde_401_com_mensagem_clara(api):
    cadastrar(api)
    resposta = entrar(api, password="senha-errada")
    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "E-mail ou senha incorretos"
    assert resposta.headers["www-authenticate"] == "Bearer"


def test_email_inexistente_responde_igual_a_senha_errada(api):
    """A mesma resposta nos dois casos: ninguém descobre quais e-mails têm conta."""
    cadastrar(api)
    errada = entrar(api, password="senha-errada")
    inexistente = entrar(api, email="ninguem@teste.com")
    assert inexistente.status_code == errada.status_code == 401
    assert inexistente.json() == errada.json()


# ---------- renovação do token ----------

def test_refresh_gera_novos_tokens_que_funcionam(api):
    cadastrar(api)
    tokens = entrar(api).json()
    resposta = api.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resposta.status_code == 200
    novo = resposta.json()
    me = api.get("/users/me", headers={"Authorization": f"Bearer {novo['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "ana@teste.com"


def test_refresh_recusa_um_access_token(api):
    cadastrar(api)
    tokens = entrar(api).json()
    resposta = api.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert resposta.status_code == 401


def test_refresh_recusa_token_invalido(api):
    assert api.post("/auth/refresh", json={"refresh_token": "isto-nao-e-um-jwt"}).status_code == 401


def test_refresh_de_usuario_que_nao_existe_mais_responde_401(api, db_session):
    usuario = cadastrar(api).json()
    refresh = create_refresh_token(usuario["id"])
    db_session.delete(db_session.get(User, usuario["id"]))
    db_session.commit()
    assert api.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 401


# ---------- rotas protegidas ----------

def test_rota_protegida_sem_token_responde_401(api):
    resposta = api.get("/users/me")
    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "Não autenticado"


def test_users_me_devolve_o_usuario_logado(api, make_user):
    usuario, headers = make_user(name="Beatriz", email="bia@teste.com")
    me = api.get("/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["id"] == usuario["id"] and me.json()["email"] == "bia@teste.com"
    assert "password_hash" not in me.json()


def test_refresh_token_nao_abre_rota_protegida(api):
    usuario = cadastrar(api).json()
    headers = {"Authorization": f"Bearer {create_refresh_token(usuario['id'])}"}
    assert api.get("/users/me", headers=headers).status_code == 401


def test_token_adulterado_responde_401(api, make_user):
    _, headers = make_user()
    token = headers["Authorization"].split()[1]
    adulterado = {"Authorization": f"Bearer {token[:-4]}AAAA"}
    assert api.get("/users/me", headers=adulterado).status_code == 401


def test_token_de_usuario_apagado_responde_401(api, db_session):
    usuario = cadastrar(api).json()
    token = create_access_token(usuario["id"])
    db_session.delete(db_session.get(User, usuario["id"]))
    db_session.commit()
    assert api.get("/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.parametrize("rota", ["/users/me", "/filters", "/stories", "/stories/1/segments", "/audio/url?key=a"])
def test_todas_as_rotas_de_dados_exigem_token(api, rota):
    assert api.get(rota).status_code == 401
