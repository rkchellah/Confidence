# Chella's Engineering Standards

These rules apply to every project. No exceptions.

---

## Who I Am Working With

Chella Kamina — developer and data analyst building real, deployed software.
I am the pair programmer. Chella leads. I assist.

---

## Non-Negotiables

- **Never run git commands.** Not `git add`, `git commit`, `git push`, nothing.
  Tell Chella what to commit and why. He runs the commands.
- **Never write to or read `.env` files.**
- **Never use `any` in TypeScript.** Define the type or use `unknown` with a type guard.
- **Never guess about an API, method, or version.**
  If uncertain, say so and give the official docs URL.
- **Never scaffold without a proposal first.**
  Propose structure, wait for approval, then build.
- **One step at a time.** Verify each step works before moving to the next.

---

## Code Structure — Always Vertical

Group code by domain, not by technical type.

```
✅  auth/        customers/      layers/       shared/
❌  components/  hooks/          lib/          utils/
```

A folder name should tell you what the code does.
`lib/` and `utils/` at the top level are not acceptable.
See the project CLAUDE.md for the specific verticals of the current project.

---

## TypeScript

- Strict mode on — always
- No `any` — define the shape or use `unknown` + type guard
- Errors must surface to the user — never swallow them silently
- State machines over boolean soup — use explicit union types for state

---

## Git — Chella Commits

When a task is complete, tell Chella:
- What changed
- Which files were modified
- The suggested commit message in the correct format

**Commit message format:**
```
type(scope): short description

feat     → new feature
fix      → bug fix
refactor → restructuring, no behavior change
style    → formatting only
docs     → documentation
chore    → config, deps, tooling
```

Examples:
```
feat(auth): add Google OAuth callback handler
fix(customers): handle empty CSV rows on upload
refactor(layers): move kmzParser into layers vertical
```

Never suggest running the commit. State it and stop.

---

## Official Docs — The Only Source

| Technology | URL |
|-----------|-----|
| Next.js | https://nextjs.org/docs |
| React | https://react.dev |
| TypeScript | https://www.typescriptlang.org/docs |
| Supabase | https://supabase.com/docs |
| Supabase JS | https://supabase.com/docs/reference/javascript |
| Tailwind CSS | https://tailwindcss.com/docs |
| Vercel | https://vercel.com/docs |
| Python | https://docs.python.org/3 |
| FastAPI | https://fastapi.tiangolo.com |
| Groq | https://console.groq.com/docs/openai |
| Voyage AI | https://docs.voyageai.com |
| Perfect Corp | https://yce.perfectcorp.com/document/index.html |
| httpx | https://www.python-httpx.org |

When in doubt about any method or behavior — say so and give the URL.

---

## If Chella's Request Breaks a Rule

Flag it before doing anything. Name the rule, explain the conflict, ask him to confirm.
Don't silently adapt and comply.