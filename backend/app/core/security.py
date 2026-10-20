from passlib.context import CryptContext

# argon2 é o algoritmo de hash de senhas definido para o projeto.
# deprecated="auto" faz o passlib marcar hashes antigos para serem refeitos se os parâmetros mudarem.
_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    """Gera o hash argon2 da senha (já com salt aleatório embutido)."""
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Confere a senha digitada contra o hash guardado. Será usada pelo login."""
    return _pwd_context.verify(password, password_hash)
