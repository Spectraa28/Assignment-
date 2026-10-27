# Running the classifier

Requires Python 3.10 or newer; no packages to install.

1. Copy `cloud-flare.sh` to `cloud-flare.local.sh`, if the local file does not exist.
2. Replace the account ID and token placeholders in that local file. Keep its format
   (`export NAME="value"`). Use a free Cloudflare account and a token restricted to
   Workers AI Read/Edit on that account. Never commit the local file.
3. Run `python classify.py` from this folder.
4. Open `report.html` in a browser and read all 100 comments. Record your own judgments
   in `MISTAKES.md`, as the assignment requires.
5. Run `python classify.py --v2` for the second set of 100 comments, using the larger
   `clef` model. Open `results-v2.html` and manually document errors in `MISTAKES-v2.md`.

The script uses Cloudflare's `@cf/cloudflare/clef-flash` for `comments.json` and
`@cf/cloudflare/clef` for `comments-v2.json`, as required by the updated assignment.
Both runs use the same criteria. Each request asks one three-choice moderation question and includes
the course name, thread title, and comment. The prompt is in `classify.py` and saved
with the results. The script does not create human labels or identify mistakes.

`results.json` (or `results-v2.json`) saves validated predictions, scores, and model token counts
after each successful call. It contains no API credentials. Rerunning resumes from
saved results; completed comments are not sent again. Changed input, model, or
instructions are rejected to prevent mixing runs. Rename the saved results if you
intend to start a fresh run, which will make new API calls.

There are at most 100 requests per dataset run, each with a 60-second timeout and
no automatic retries. An API or network error stops the run. If any predictions were
saved, the HTML report marks the remaining comments as pending. For HTTP 429, wait
and check your quota before rerunning. Stay on the free plan; the script does not
inspect your billing plan or enforce a monetary cap.

To regenerate HTML without sending any requests: `python classify.py --report-only`.
For the second dataset: `python classify.py --v2 --report-only`.
To run the offline checks: `python -m unittest -v`.

# Tools used

Codex helped write the Python classifier, HTML report generator, offline tests, and
these run instructions. The implementation uses only Python's standard library.
Codex also formatted my review entries using the labels and explanations I supplied;
the review judgments are my own.
Cloudflare's Clef Flash and Clef are the models used to classify the two datasets. The
assignment's API guide and Cloudflare's official REST API/model documentation were
consulted. Offline tests use synthetic comments and mocked API responses; they are
not evidence of live model quality.

# Personal reflection

The easy part for me was generally telling which comments were genuine questions
that needed attention and which were not. What surprised me was that the classifier
marked some genuine comments as toxic. I think a human needs to inspect the results
so that genuine comments are not hidden.

# Execution status

Both live Cloudflare runs completed on 2026-10-27: 100 saved predictions from
Clef Flash for the first dataset and 100 from Clef for the second. Both HTML
reports were generated from those responses. Seven offline tests pass. These
checks cover the program's behavior, not the accuracy of the model's decisions.
I completed my review of both reports. `MISTAKES.md` contains four disagreements;
`MISTAKES-v2.md` contains three disagreements, including one marked borderline
because the account's authenticity is unverified. The reports have not
been visually checked in a browser by Codex because browser access was unavailable.
