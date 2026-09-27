# **Le**cturfier **Qu**otes

Discord bot for storing and retrieving quotes.

## Setup

Create a `.env` containing `DISCORD_TOKEN=...` (optionally `DB_PATH=...`, default `data/quotes.db`), then:

```
just upgrade   # create or migrate the database
just bot       # run the bot
```

## Adding quotes

- `/add` — add a quote. Omit arguments to be prompted with a form, or pass `member`/`name` and `text` directly.
- **Add Quote** (message context menu) — quote the selected message.
- `<prefix>q` or `<prefix>quote` in reply to a message (default prefix `$`).
- React with a configured quote emoji (by default any custom emoji named `AddQuote`).

Quotes added from a message store that message's id, so the same message can only be quoted once — repeat reactions, concurrent adds and restarts cannot create duplicates.

## Commands

| Command | Description |
| --- | --- |
| `/add [member] [name] [text]` | Add a quote |
| `/quote [id]` | Show a quote (random if no id) |
| `/quotes [user] [ephemeral]` | List a user's quotes |
| `/search <query>` | Search quotes with autocomplete |
| `/favorites list\|add\|remove` | Manage your own favorites |
| `/report <quote_id>` | Report a quote for deletion |
| `/reports` | Review reports and delete or dismiss them *(Manage Server)* |
| `/config prefix [value]` | Set the command prefix *(Manage Server)* |
| `/config emojis add\|remove\|list` | Configure quote emojis *(Manage Server)* |

Quotes shown by `/quote` and `/search` carry a ⭐ button that toggles the quote in the clicking user's favorites.
