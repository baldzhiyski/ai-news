from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .email_reader import EmailItem
from .link_fetcher import ArticleInfo, IgnoredLink


REPORT_SECTIONS = (
    "AI engineering and developer tools",
    "AI agents and automation",
    "Startups, products, and business opportunities",
    "Research or technical breakthroughs",
    "Market signals and trends",
)


@dataclass(frozen=True)
class WeeklyReport:
    subject: str
    body: str


def generate_weekly_report(
    *,
    emails: list[EmailItem],
    articles: list[ArticleInfo],
    ignored_links: list[IgnoredLink],
    date_range: str,
) -> WeeklyReport:
    subject = f"Weekly AI Intelligence Brief — {date_range}"
    processed_link_count = len(articles)
    ignored_count = len(ignored_links)
    articles_by_topic = _group_by_topic(articles)
    top_articles = sorted(articles, key=lambda article: article.relevance_score, reverse=True)[:5]

    lines: list[str] = [
        "Executive summary",
        _executive_summary(articles, ignored_count),
        "",
        "Top 5 most important developments",
        *_format_top_developments(top_articles),
        "",
    ]

    for section in REPORT_SECTIONS:
        lines.append(section)
        lines.extend(_format_topic_section(articles_by_topic.get(section, [])))
        lines.append("")

    lines.extend(
        [
            "Actionable ideas for my own AI/startup projects",
            *_actionable_ideas(articles),
            "",
            "Links worth reading",
            *_links_worth_reading(articles),
            "",
            "Ignored/noisy items summary",
            _ignored_summary(ignored_links),
            "",
            "Processed email count and processed link count",
            f"Processed emails: {len(emails)}",
            f"Processed useful links: {processed_link_count}",
        ]
    )

    return WeeklyReport(subject=subject, body="\n".join(lines).strip() + "\n")


def _executive_summary(articles: list[ArticleInfo], ignored_count: int) -> str:
    if not articles:
        return (
            "No useful AI-related external articles were extracted from the allowlisted Gmail "
            f"labels. {ignored_count} noisy or unsafe links were ignored."
        )

    topics = Counter(article.main_topic for article in articles)
    dominant = ", ".join(topic.lower() for topic, _ in topics.most_common(3))
    strongest = max(articles, key=lambda article: article.relevance_score)
    return (
        f"This week's signal clusters around {dominant}. The strongest item is "
        f"'{strongest.title}' from {strongest.source}, which matters because it connects to "
        f"{strongest.relevance}. Across the set, prioritize developments that reduce AI product "
        "delivery friction, create automation leverage, or reveal where infrastructure and startup "
        "budgets are moving."
    )


def _format_top_developments(articles: list[ArticleInfo]) -> list[str]:
    if not articles:
        return ["- No high-confidence developments found."]
    lines = []
    for index, article in enumerate(articles, start=1):
        claim = article.key_claims[0] if article.key_claims else "The item contains AI-relevant signal."
        lines.append(
            f"{index}. {article.title} ({article.source}) - {claim} Why it matters: {article.relevance}."
        )
    return lines


def _format_topic_section(articles: list[ArticleInfo]) -> list[str]:
    if not articles:
        return ["- No strong signal in this category from the processed links."]
    lines = []
    for article in sorted(articles, key=lambda item: item.relevance_score, reverse=True)[:4]:
        claims = " ".join(article.key_claims[:2])
        lines.append(f"- {article.title}: {claims}")
    return lines


def _actionable_ideas(articles: list[ArticleInfo]) -> list[str]:
    topics = Counter(article.main_topic for article in articles)
    ideas = []
    if topics["AI engineering and developer tools"]:
        ideas.append(
            "- Audit repetitive engineering workflows that could become small internal AI tools with measurable time savings."
        )
    if topics["AI agents and automation"]:
        ideas.append(
            "- Prototype one constrained agent workflow with clear human approval points and logs before expanding autonomy."
        )
    if topics["Startups, products, and business opportunities"]:
        ideas.append(
            "- Map the recurring customer pain points in these articles to narrow product wedges and paid pilot candidates."
        )
    if topics["Research or technical breakthroughs"]:
        ideas.append(
            "- Turn one technical advance into a benchmark or demo that tests whether it changes cost, latency, or quality."
        )
    if topics["Market signals and trends"]:
        ideas.append(
            "- Track whether market signals point to budget shifting toward infrastructure, workflow automation, or vertical AI."
        )
    return ideas or ["- No specific actions emerged from this run; keep the labels narrow and source quality high."]


def _links_worth_reading(articles: list[ArticleInfo]) -> list[str]:
    if not articles:
        return ["- None."]
    return [
        f"- {article.title} - {article.url}"
        for article in sorted(articles, key=lambda item: item.relevance_score, reverse=True)[:10]
    ]


def _ignored_summary(ignored_links: list[IgnoredLink]) -> str:
    if not ignored_links:
        return "No links were ignored."
    counts = Counter(link.reason for link in ignored_links)
    return "; ".join(f"{reason}: {count}" for reason, count in counts.most_common())


def _group_by_topic(articles: list[ArticleInfo]) -> dict[str, list[ArticleInfo]]:
    grouped: dict[str, list[ArticleInfo]] = defaultdict(list)
    for article in articles:
        grouped[article.main_topic].append(article)
    return dict(grouped)
