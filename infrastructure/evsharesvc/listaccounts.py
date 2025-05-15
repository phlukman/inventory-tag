import boto3

org_client = boto3.client('organizations')

def list_accounts_for_parent(parent_id):
    accounts = []
    response = org_client.list_accounts_for_parent(ParentId=parent_id)
    accounts.extend(response['Accounts'])
    child_ous = org_client.list_organizational_units_for_parent(ParentId=parent_id)
    for ou in child_ous['OrganizationalUnits']:
        ou_accounts = list_accounts_for_parent(ou['Id'])
        accounts.extend(ou_accounts)
        print(f"Accounts under OU {ou['Name']} {ou['Id']}")
        for account in ou_accounts:
            print(f"{account['Id']} {account['Name']}")
    return accounts

def list_ous_and_accounts(parent_id):
    child_ous = org_client.list_organizational_units_for_parent(ParentId=parent_id)
    for ou in child_ous['OrganizationalUnits']:
        ou_accounts = list_accounts_for_parent(ou['Id'])
        ou_account_lists[ou['Name']] = ou_accounts
        print(f"Account under OU {ou['Name']} {ou['Id']}")
        for account in ou_accounts:
            print(f"{account['Id']} {account['Name']}")
        list_ous_and_accounts(ou['Id'])

#root_response = org_client.list_roots()
#root_id = root_response['Roots'][0]['Id']

sandbox_ou_id  ="ou-ws49-sic5kz5l"
nonprod_ou_id  = "ou-ws49-moj4w8y8"
prod_ou_id  = "ou-ws49-1oy4sz8l"
root_id = prod_ou_id

ou_account_lists = {}
all_accounts = []
list_ous_and_accounts(root_id)
for ou_name, accounts in ou_account_lists.items():
    all_accounts.extend(accounts)

print("\n### Combined list of all accounts:")
for account in all_accounts:
    print(f"{account['Id']} : {account['Name']}")
print("[", end='')
for account in all_accounts:
    print(f"\"{account['Id']}\",", end=" ")
print("]")