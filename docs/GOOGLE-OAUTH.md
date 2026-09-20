# Google: giving the agent its own key to one inbox

About four minutes. Do this on a machine with a browser.

## The clicks

At [console.cloud.google.com](https://console.cloud.google.com), **logged in as the address the agent will send from**. Check the account avatar in the top right before you start. If you have both a personal address and a work one, picking the wrong account here is the most common way this goes wrong.

1. New project. Name it anything. Use a new project, not one you already rely on.
2. **APIs & Services → Enable APIs** → search **Gmail API** → Enable.
3. **OAuth consent screen** → External → fill the three required fields (app name, support email, developer email).
4. Under **Test users**, add your own address.
5. **PUBLISH APP.** This is the one that matters. See below.
6. **Credentials → Create credentials → OAuth client ID** → Application type **Desktop app**.
7. Download the JSON. Rename it `client_secret.json`. Put it in `~/.config/inbox-agent/` and `chmod 600` it.

## "Access blocked: can only be used within its organization" (Error 403: org_internal)

The project belongs to a Google Workspace organization and its consent screen audience is set to **Internal**, so only addresses on that company domain may authorize it. You are logging in with an address outside it, usually a personal gmail.

Two ways out:

- **Easiest.** Make a new project while signed in as the address the agent will actually use. A personal gmail account is not in an organization, so the Internal option does not exist and the problem cannot happen.
- **Or** open that project's OAuth consent screen, find the audience setting, switch it from Internal to External, and publish. Only do this to a project nothing else depends on.

## The seven day thing

If the app is left in **Testing**, Google expires the login after seven days. No error, no warning. It works perfectly for a week and then quietly stops, which is why people never work out what happened.

Pressing **Publish** on a desktop app that only you use does not put you through review and does not expose anything. Do it at step five, before the key exists.

## Log in

```
gsend auth        # opens a browser, log in as the configured address
gsend whoami      # prints the address the token belongs to
gsend test        # sends one email to yourself and prints the From header it used
```

`test` has to print `VERIFIED`. If it prints anything else, do not go further. The token is the sender identity, and gsend refuses to run if it does not match `gmail_address` in your config.

## On a server with no screen

`gsend auth` needs a browser, so do the whole of this page on your laptop first. Then push three files up:

```
ssh agent@YOUR_SERVER_IP 'mkdir -p ~/.config/inbox-agent'
scp ~/.config/inbox-agent/client_secret.json \
    ~/.config/inbox-agent/token.json \
    agent@YOUR_SERVER_IP:~/.config/inbox-agent/
```

Then on the server, `gsend whoami` and `gsend test` again. Prove it twice.

Google's old "paste the code back" login for headless machines is gone. Do not go looking for it.

## Scopes

The token asks for three: send, compose, readonly. It cannot delete mail, change labels, or touch settings. `gsend` never asks for more.
