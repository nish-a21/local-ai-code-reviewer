def get_user(username):
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    result = db.execute(query)
    return result

def divide(a, b):
    return a / b

password = "admin123"
