# **Le**cturfier **Qu**otes

Discord bot for storing and retrieving quotes.

## Setup

Create a `.env` containing `DISCORD_TOKEN=...` (optionally `DB_PATH=...`, default `data/quotes.db`), then:

```
just upgrade   # create or migrate the database
just bot       # run the bot
```

## Adding quotes

- `/add` — add a quote. Omit arguments to be prompted with a form, or pass `member`/`name` and `text` directly. Length is limited by `/admin max-quote-length` (default 500).
- **Add Quote** (message context menu) — quote the selected message.
- `<prefix>q` or `<prefix>quote` (default prefix `$`, see `/admin prefix`):
  - as a reply to a message, quotes that message;
  - on its own, shows a random quote;
  - `<user>` shows a random quote from that user;
  - `all <user>` or `<user> all` lists that user's quotes;
  - `<user> <text>` adds a quote for that user.
  - `<user>` may be a mention, a Discord ID, a named user, or an alias.
- React with a configured quote emoji (by default any custom emoji named `AddQuote`).

Quotes added from a message store that message's id, so the same message can only be quoted once — repeat reactions, concurrent adds and restarts cannot create duplicates.

## Commands

| Command                            | Description                                                 |
| ---------------------------------- | ----------------------------------------------------------- |
| `/add [member] [name] [text]`      | Add a quote                                                 |
| `/quote [id]`                      | Show a quote (random if no id)                              |
| `/quotes [user] [ephemeral]`       | List a user's quotes                                        |
| `/search <query>`                  | Search quotes with autocomplete                             |
| `/favorites list\|add\|remove`     | Manage your own favorites                                   |
| `/report <quote_id>`               | Report a quote for deletion                                 |
| `/alias add <name> <alias>`        | Add an alias for a named user                               |
| `/alias remove <alias>`            | Remove an alias                                             |
| `/admin reports`                   | Review reports and delete or dismiss them *(Manage Server)* |
| `/admin max-quote-length [value]`  | Set the max quote length *(Manage Server)*                  |
| `/admin prefix [value]`            | Set the command prefix *(Manage Server)*                    |
| `/admin emojis add\|remove\|list`  | Configure quote emojis *(Manage Server)*                    |

Quotes shown by `/quote` and `/search` carry a ⭐ button that toggles the quote in the clicking user's favorites.
