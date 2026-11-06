# How the evaluation questions are labeled

Each question lists the page(s) that **contain the answer**. A page that only links to the
answer, or only names the relevant class, does not count.

Questions were written in a developer's words, without looking at the indexed chunks.
Every label was then checked by hand against the docs text (2026-11-06). That audit changed
four labels (three in the table, one below):

| Question | Change | Reason |
|---|---|---|
| Swap the real database dependency for a fake one during tests | removed `how-to/testing-database.md` | That page is three links to the SQLModel docs and doesn't explain overrides |
| Can I still use a database session from a yield dependency inside a background task? | `tutorial/dependencies/dependencies-with-yield.md` -> `advanced/advanced-dependencies.md` | The tutorial page only links to the advanced page, which has the answer (create a new session inside the task) |
| Return XML instead of JSON from one endpoint | removed `advanced/custom-response.md` | That page never mentions XML; `advanced/response-directly.md` has the XML example |

Considered and rejected: accepting `reference/staticfiles.md` for "Serve images and CSS files
from a folder". It names the `StaticFiles` class but links to the tutorial for how to use it.

Found later while recording the demo: `tutorial/header-param-models.md` has its own "Disable
Convert Underscores" section, so it was added as a correct answer for "Stop FastAPI from
turning underscores into hyphens in a header name".
