def get_user(username):
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    result = db.execute(query)
    return result
