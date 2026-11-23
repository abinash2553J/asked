from pydantic import BaseModel, Field


class Comment(BaseModel):
    text: str
    author: str = ""
    likes: int = 0
    published: str = ""
    is_reply: bool = False


class VideoMeta(BaseModel):
    video_id: str
    url: str
    title: str = ""
    author: str = ""


class ContentIdea(BaseModel):
    title: str
    angle: str = ""


class QuestionCluster(BaseModel):
    rank: int = 0
    canonical: str
    count: int
    likes: int = 0
    examples: list[Comment] = Field(default_factory=list)
    ideas: list[ContentIdea] = Field(default_factory=list)
    source: str = "template"


class Stats(BaseModel):
    comments_fetched: int = 0
    comments_analyzed: int = 0
    questions: int = 0
    groups: int = 0
    capped: bool = False
    llm: bool = False
    elapsed_ms: int = 0


class AnalysisResult(BaseModel):
    video: VideoMeta
    clusters: list[QuestionCluster] = Field(default_factory=list)
    stats: Stats = Field(default_factory=Stats)
    generated_at: str = ""
