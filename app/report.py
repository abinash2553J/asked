from .models import AnalysisResult, Comment

MD_SPECIALS = "\\`*_{}[]<>#+-.!|"


def _md(text: str) -> str:
    return "".join(f"\\{ch}" if ch in MD_SPECIALS else ch for ch in text)


def _quote(comment: Comment) -> str:
    body = " ".join(comment.text.split())
    who = comment.author or "a viewer"
    return f"> {body}\n>\n> — {_md(who)}"


def render_markdown(result: AnalysisResult) -> str:
    video = result.video
    stats = result.stats
    title = video.title or "Untitled video"
    lines: list[str] = [
        f"# {_md(title)}",
        "",
        f"**{_md(video.author or 'Unknown channel')}** · [Watch on YouTube]({video.url})",
        "",
        f"_{stats.comments_analyzed} comments analyzed · {stats.questions} questions · "
        f"{stats.groups} groups · {result.generated_at[:10]}_",
        "",
        "## What people keep asking",
        "",
    ]

    if not result.clusters:
        lines += ["No repeated questions found in these comments yet.", ""]

    for cluster in result.clusters:
        lines += [
            f"### {cluster.rank}. {_md(cluster.canonical)}",
            "",
            f"**{cluster.count}× asked** · {cluster.likes} likes across the group",
            "",
        ]
        for comment in cluster.examples:
            lines += [_quote(comment), ""]
        if cluster.ideas:
            lines.append("**Ideas**")
            lines.append("")
            for idea in cluster.ideas:
                angle = f" — {_md(idea.angle)}" if idea.angle else ""
                lines.append(f"- **{_md(idea.title)}**{angle}")
            lines.append("")

    lines += ["## Content ideas", ""]
    slate = [(cluster.canonical, idea) for cluster in result.clusters for idea in cluster.ideas]
    if not slate:
        lines.append("No ideas drafted yet.")
    for i, (question, idea) in enumerate(slate, start=1):
        angle = f" — {_md(idea.angle)}" if idea.angle else ""
        lines.append(f"{i}. **{_md(idea.title)}**{angle}  \n   <sub>from: {_md(question)}</sub>")

    lines += [
        "",
        "---",
        "",
        f"Generated from {stats.comments_analyzed} comments"
        + (" (capped)" if stats.capped else "")
        + f" · ideas phrased by {'LLM' if stats.llm else 'templates'}",
        "",
    ]
    return "\n".join(lines)
