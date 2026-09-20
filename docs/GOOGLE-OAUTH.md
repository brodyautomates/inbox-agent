# Google: giving the agent its own key to one inbox

About four minutes. Do this on a machine with a browser.

## Which path you are on

Two kinds of Google account, two different amounts of work. Check which you have before you start.

**A work account on your own domain (Google Workspace).** Set the audience to **Internal**. Only people on your domain can log in, which is just you. No publishing, no verification, no warning screen, and the login does not expire. Skip to step 6.

**A plain gmail.com address.** Your account belongs to no organization, so Internal does not exist as an option. You take the External path below: publish the app, and click through one warning at login. It is four extra clicks and it is permanent once done.

## The clicks

At [console.cloud.google.com](https://console.cloud.google.com), **logged in as the address the agent will send from**. Check the account avatar in the top right before you start. If you have both a personal address and a work one, picking the wrong account here is the most common way this goes wrong.

1. New project. Name it anything. Use a new project, not one you already rely on.
2. **APIs & Services → Enable APIs** → search **Gmail API** → Enable.
3. **OAuth consent screen**, called **Google Auth Platform** in the newer console. On **Branding**, fill in app name, user support email, and the developer contact email at the bottom. Do not upload a logo and leave the home page, privacy policy, terms and authorized domain fields empty. A logo forces the app into Google's verification process.
4. **Audience** → set it to **External**. A personal gmail account has no other option, which is correct.
5. On that same Audience page, **Publish app**, and confirm. Status must read "In production", not "Testing". This is the one that matters. See below.
6. **Clients** → **Create client** → Application type **Desktop app** → Create → **Download JSON**. In the older console this lives under **APIs & Services → Credentials**. If you close the panel, the download icon is on the client's row in the list.
7. The file lands in Downloads named `client_secret_....json`. It belongs at `~/.config/inbox-agent/client_secret.json`, owner-read-only:

```
mv ~/Downloads/client_secret_*.json ~/.config/inbox-agent/client_secret.json
chmod 600 ~/.config/inbox-agent/client_secret.json
```

## "Access blocked: can only be used within its organization" (Error 403: org_internal)

The project belongs to a Google Workspace organization and its consent screen audience is set to **Internal**, so only addresses on that company domain may authorize it. You are logging in with an address outside it, usually a personal gmail.

Two ways out:

- **Easiest.** Make a new project while signed in as the address the agent will actually use. A personal gmail account is not in an organization, so the Internal option does not exist and the problem cannot happen.
- **Or** open that project's OAuth consent screen, find the audience setting, switch it from Internal to External, and publish. Only do this to a project nothing else depends on.

## Publish is greyed out

Things to check on the **Branding** page, in order:

1. **No app logo.** Google's own note there says uploading one means the app must go through verification unless it is Internal or stays in Testing. Clear the field. An app with one user does not need a logo.
2. **Developer contact email is filled in** and saved.
3. Home page, privacy policy, terms of service and authorized domains all **empty**. They exist for verification, which you are not doing.
4. On **Data Access**, no Gmail scopes listed. A Desktop app requests its permissions at login, so it does not need them declared here.

If all four are true and the button is still greyed out, do not keep fighting it. Use the test user path below, which works immediately, and come back to publishing later. Google's console does not explain this one and the state can be stale for a while after a change.

**The test user path.** Audience page → **Test users** → **Add users** → your address → Save. The login works straight away. The cost is that a Testing app's login expires after seven days, so publish before you depend on it.

## "has not completed the Google verification process" (Error 403: access_denied)

The app is still in **Testing** and your address is not on its tester list. On the **Audience** page, press **Publish app** and confirm. Status changes to "In production" and the login works straight away.

The alternative, adding yourself under **Test users** on the same page, also works but leaves you in Testing, where the login expires after seven days. Publish instead.

At the login you will then see "Google hasn't verified this app". Click **Advanced**, then continue. Verification is for apps with real user bases. This one has one user.

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
