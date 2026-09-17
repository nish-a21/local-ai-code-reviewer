def add_item(item, item_list=[]):
    item_list.append(item)
    return item_list

# Let's test the function
print(add_item("apple"))   # Expected: ['apple']
print(add_item("banana"))  # Expected: ['banana']
print(add_item("cherry"))  # Expected: ['cherry']
