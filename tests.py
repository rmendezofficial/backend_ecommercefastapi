from routers.users import pwd_context


def get_password_hash(password):
    print(f'{password}:{pwd_context.hash(password)}')
    
get_password_hash('contrasena')