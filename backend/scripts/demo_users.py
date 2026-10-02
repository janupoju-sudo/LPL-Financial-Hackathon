"""Create the demo users in Cognito and print an ID token for each (for curl / Postman testing).

Usage:  python scripts/demo_users.py --user-pool-id us-east-1_XXX --client-id YYY [--password 'Demo!2345']
"""
import argparse

import boto3

USERS = [
    ("maya@harborpoint.example", "owner"),
    ("raj@harborpoint.example", "partner"),
    ("dev@harborpoint.example", "ops"),
    ("priya@lpl-demo.example", "lpl_bookkeeper"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-pool-id", required=True)
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--password", default="Demo!2345")
    ap.add_argument("--practice", default="p1")
    args = ap.parse_args()
    idp = boto3.client("cognito-idp")
    for email, group in USERS:
        try:
            idp.admin_create_user(
                UserPoolId=args.user_pool_id, Username=email, MessageAction="SUPPRESS",
                UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"},
                                {"Name": "custom:practiceId", "Value": args.practice}],
            )
        except idp.exceptions.UsernameExistsException:
            pass
        idp.admin_set_user_password(UserPoolId=args.user_pool_id, Username=email,
                                    Password=args.password, Permanent=True)
        idp.admin_add_user_to_group(UserPoolId=args.user_pool_id, Username=email, GroupName=group)
        token = idp.admin_initiate_auth(
            UserPoolId=args.user_pool_id, ClientId=args.client_id, AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": args.password},
        )["AuthenticationResult"]["IdToken"]
        print(f"\n# {group}: {email}\nexport TOKEN_{group.upper()}='{token}'")


if __name__ == "__main__":
    main()
