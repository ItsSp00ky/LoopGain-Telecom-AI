"""The worked example the other components copy, and the check they run first (T20).

The chatbot and the copilot call the service over HTTP and never import this package
(decision 17).
So this module is written to be copied into their repositories rather than imported from
ours: it uses only the standard library, it takes its keys and its base URL as arguments,
and it holds no state.
A component that imported it would be back inside our package, which is the seam T20
exists to prove is unnecessary.

`check` runs every call a consumer makes and every refusal it has to handle, against a
running service, and reports what came back.
`churn check-integration` prints that report.
That is the acceptance evidence for T20: not that our tests pass, but that somebody
standing outside this repository, holding only a key and a subscriber ID, gets the
answers the contract promises.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

# Copied from `api.py` rather than imported, because a copy of this file lives outside
# this repository and has nothing to import from. `test_client.py` compares the two, so
# the copy cannot drift silently.
API_KEY_HEADER = "X-API-Key"

# Long enough for a cold service that is loading a bundle, short enough that a chatbot
# turn does not hang on a service that is not coming back.
TIMEOUT_SECONDS = 10


class ServiceError(RuntimeError):
    """The service refused or could not be reached; `status` is its code, if it answered."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def get(base_url: str, path: str, api_key: str | None = None, timeout=TIMEOUT_SECONDS) -> dict:
    """GET one path and decode the answer.

    Every failure becomes a `ServiceError` carrying the status and the service's own
    explanation, because the consumer that has to act on it is a language model's tool
    call: "not authorized for this endpoint" is something it can report to a person,
    while a raw traceback is not.
    """
    request = urllib.request.Request(base_url.rstrip("/") + path)
    if api_key:
        request.add_header(API_KEY_HEADER, api_key)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise ServiceError(f"{path} answered {error.code}: {_detail(error)}", error.code) from error
    except urllib.error.URLError as error:
        raise ServiceError(
            f"{base_url} did not answer ({error.reason}). Is `churn serve` running there?"
        ) from error


def _detail(error: urllib.error.HTTPError) -> str:
    """The service's `detail` message, or the raw body when the error came from elsewhere."""
    body = error.read().decode("utf-8", "replace")
    try:
        return str(json.loads(body).get("detail", body))
    except json.JSONDecodeError:
        return body.strip() or error.reason


def health(base_url: str) -> dict:
    """Readiness. No key: a liveness probe has no secret to offer, and this holds no data."""
    return get(base_url, "/health")


def catalogue(base_url: str, chatbot_key: str) -> list[dict]:
    """Every operator package the chatbot may talk about (T16)."""
    return get(base_url, "/catalogue", chatbot_key)["offers"]


def _found(base_url: str, path: str, api_key: str) -> dict | None:
    """GET something that may legitimately not exist; 404 becomes None."""
    try:
        return get(base_url, path, api_key)
    except ServiceError as error:
        if error.status == 404:
            return None
        raise


def offer_for(base_url: str, chatbot_key: str, subscriber_id: str) -> dict | None:
    """The approved offer for one subscriber, or None when there is none.

    404 is the one answer for every case the chatbot must treat the same way: no
    campaign, no proposal, a proposal nobody reviewed, and a proposal a reviewer
    rejected. Distinguishing them would tell the customer an offer was considered and
    refused, so this returns None for all of them and the chatbot says nothing either
    way.
    """
    return _found(base_url, f"/subscribers/{_quote(subscriber_id)}/retention", chatbot_key)


def risk_for(base_url: str, copilot_key: str, subscriber_id: str) -> dict | None:
    """One subscriber's risk, reasons and value, or None when the export does not hold them.

    This 404 means what it says: the subscriber was not scored. Nothing is being hidden,
    unlike the chatbot's 404 above.
    """
    return _found(base_url, f"/subscribers/{_quote(subscriber_id)}/risk", copilot_key)


def _quote(subscriber_id: str) -> str:
    return urllib.parse.quote(str(subscriber_id), safe="")


def portfolio_summary(base_url: str, copilot_key: str) -> dict:
    """Customers and LYD at risk by risk band and value tier, with the model's evidence."""
    return get(base_url, "/portfolio/summary", copilot_key)


def offer_sentence(offer: dict | None) -> str:
    """What a chatbot may say about that answer, with the field each part came from.

    The rule the other components asked for in one line: the words are the operator's,
    the model chose nothing here, and an empty answer stays empty.
    """
    if offer is None:
        return "No approved offer [404]: say there is nothing today, and offer nothing else."
    package = offer.get("offer") or {}
    name = package.get("name_ar") or package.get("name_en") or offer["recommended_offer_id"]
    reason = offer.get("offer_reason_ar") or offer.get("offer_reason_en") or ""
    return f"{reason} [offer_reason_ar] - {name} [offer.name_ar]"


@dataclass
class CheckResult:
    """The report a consumer pastes into T20, and the failures that made it fail."""

    lines: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        result = (
            "Every check passed."
            if not self.failures
            else f"{len(self.failures)} checks failed: " + "; ".join(self.failures)
        )
        return "\n".join([*self.lines, "", result])

    def expect(self, name: str, expected: int, call) -> None:
        """Call something that must be refused, and record whether it was.

        A consumer's own tests cannot prove this: only the running service knows whether
        the chatbot key really is refused on the copilot's endpoint.
        """
        try:
            call()
            got: int | str = "an answer"
        except ServiceError as error:
            got = error.status or str(error)
        passed = got == expected
        self.lines.append(f"- {name}: expected {expected}, got {got}{'' if passed else '  <-'}")
        if not passed:
            self.failures.append(name)


def check(base_url: str, chatbot_key: str, copilot_key: str, subscriber_id: str) -> CheckResult:
    """Run the whole contract against a running service and report what came back."""
    result = CheckResult()
    state = health(base_url)
    if state["status"] != "ok":
        result.failures.append("service health is degraded")
    outputs = state["latest_outputs"]
    result.lines += [
        f"# Integration check of {base_url}",
        "",
        "## Health, without a key",
        f"- status: {state['status']}"
        + (f" ({'; '.join(state['problems'])})" if state["problems"] else ""),
        f"- model: {state['model_version']}, bundle loaded {state['bundle_loaded']}, "
        f"smoke prediction {state['smoke_prediction_passed']}",
        f"- serving {outputs['subscribers_in_portfolio']} subscribers and "
        f"{outputs['approved_offers']} approved offers from campaign {outputs['campaign_id']}",
        "",
        "## Chatbot, with the chatbot key",
    ]
    packages = catalogue(base_url, chatbot_key)
    first = packages[0] if packages else {}
    result.lines += [
        f"- /catalogue: {len(packages)} packages, for example {first.get('offer_id')} "
        f"({first.get('name_en')}) at {first.get('price_lyd')} LYD, collected "
        f"{first.get('collected')}",
    ]
    offer = offer_for(base_url, chatbot_key, subscriber_id)
    result.lines += [
        f"- /subscribers/{subscriber_id}/retention: "
        + (
            f"{offer['recommended_offer_id']}, approved {offer['reviewed_at']}"
            if offer
            else "no approved offer (404)"
        ),
        f"- the chatbot may say: {offer_sentence(offer)}",
        "",
        "## Copilot, with the copilot key",
    ]
    portfolio = portfolio_summary(base_url, copilot_key)
    if not portfolio["risk_available"]:
        result.failures.append("portfolio risk is unavailable")
    if portfolio["release_gate_passed"] is not True:
        result.failures.append("model release gate has not passed")
    bands = ", ".join(
        f"{group['name']} {group['customers']}" for group in portfolio["by_risk_band"]
    )
    at_risk = sum(group["lyd_at_risk"] or 0 for group in portfolio["by_risk_band"])
    risk_text = f"{at_risk:,.0f}" if portfolio["risk_available"] else "unavailable"
    passed = sum(threshold["passed"] for threshold in portfolio["success_thresholds"].values())
    found = risk_for(base_url, copilot_key, subscriber_id)
    result.lines += [
        f"- /portfolio/summary: {portfolio['subscribers']} subscribers, risk available "
        f"{portfolio['risk_available']}, scored {portfolio['scored_at']}",
        f"- by risk band: {bands}",
        f"- LYD at risk: {risk_text} (12-month scenario weighted by churn probability)",
        f"- release gate: {portfolio['release_gate_passed']}, "
        f"{passed} of {len(portfolio['success_thresholds'])} success thresholds passed",
        f"- /subscribers/{subscriber_id}/risk: "
        + (
            f"{found['risk_band']} risk, probability {found['churn_probability']}, tier "
            f'{found["value_tier"]}, first reason "{(found["reasons"] or ["none"])[0]}"'
            if found
            else "not in the scored export (404)"
        ),
        "",
        "## Refusals, which every consumer has to handle",
    ]
    result.expect(
        "the copilot's endpoint with the chatbot key",
        403,
        lambda: portfolio_summary(base_url, chatbot_key),
    )
    result.expect(
        "a chatbot endpoint with the copilot key", 403, lambda: catalogue(base_url, copilot_key)
    )
    result.expect(
        "the copilot's subscriber lookup with the chatbot key",
        403,
        lambda: get(base_url, f"/subscribers/{_quote(subscriber_id)}/risk", chatbot_key),
    )
    result.expect("a chatbot endpoint with no key", 401, lambda: get(base_url, "/catalogue"))
    result.expect(
        "a subscriber ID shaped like a phone number",
        422,
        lambda: get(base_url, "/subscribers/0912345678/retention", chatbot_key),
    )
    return result
