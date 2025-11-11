from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models
from django.utils import timezone
import os

class User(AbstractUser):
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    credits = models.PositiveIntegerField(default=50)  # initial grant
    onboarding_completed = models.BooleanField(default=False)

    def __str__(self):
        return self.username

class Onboarding(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="onboarding")
    # Lightweight initial details; we’ll extend later
    writing_style_keywords = models.CharField(max_length=255, blank=True)
    goals = models.TextField(blank=True)
    industry = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    topical_keywords = models.TextField(blank=True, help_text="Comma or newline separated topics you usually cover")
    bio = models.TextField(blank=True, help_text="Short description about yourself/brand")
    style_self_desc = models.TextField(blank=True, help_text="How you describe your writing style (optional)")
    created_at = models.DateTimeField(auto_now_add=True)

def user_upload_path(instance, filename):
    # media/user_<id>/<filename>
    return f"user_{instance.user_id}/{filename}"

class Upload(models.Model):
    SOURCE_CHOICES = (
        ("FILE", "File"),
        ("TEXT", "Typed"),
    )
    FILE_TXT = "TXT"
    FILE_PDF = "PDF"
    FILE_TEXT = "TEXT"
    FILE_TYPES = [
        (FILE_TXT, "Text (.txt)"),
        (FILE_PDF, "PDF (.pdf)"),
        (FILE_TEXT, "Typed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploads"
    )

    file = models.FileField(upload_to="uploads/", null=True, blank=True)
    file_type = models.CharField(max_length=5, choices=FILE_TYPES)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="FILE")

    bytes = models.PositiveIntegerField(default=0)
    text_extract = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def filename(self):
        return os.path.basename(self.file.name) if self.file else "(typed post)"

    def __str__(self):
        return f"{self.user.username} - {self.filename}"

class StyleProfile(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="style_profiles")
    version = models.PositiveIntegerField(default=1)
    summary_json = models.JSONField(default=dict)   # v0: simple stats; later: GPT summary
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    fun_facts = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]

class CreditTransaction(models.Model):
    KIND_CHOICES = [
        ("TOPUP", "Top-up / Added manually"),
        ("GEN", "Content Generation"),
        ("IMPROVE", "Improve Action"),
        ("STYLE", "Style Profile Regeneration"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="credit_transactions")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    amount = models.IntegerField()   # + for credit, − for debit
    balance_after = models.IntegerField()
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username}: {self.kind} ({self.amount})"

class ContentItem(models.Model):
    TYPE_BLOG = "BLOG"
    TYPE_LI = "LINKEDIN"
    TYPE_CHOICES = [(TYPE_BLOG, "Blog"), (TYPE_LI, "LinkedIn")]

    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVED = "APPROVED"
    STATUS_PUBLISHED = "PUBLISHED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_PUBLISHED, "Published"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="content_items")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    topic = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_type_display()} - {self.topic}"

class ContentVersion(models.Model):
    content = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField()
    body_md = models.TextField()       # markdown string
    meta_json = models.JSONField(default=dict)  # e.g., meta title/description/keywords for blogs
    created_at = models.DateTimeField(auto_now_add=True)
    hero_image_url = models.URLField(blank=True, null=True)
    hero_image_prompt = models.TextField(blank=True, null=True)
    image_search_term = models.CharField(max_length=120, blank=True, default="")
    image_search_term_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("content", "version_no")
        ordering = ["-version_no", "-created_at"]

class GuidelinePillar(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pillars")
    title = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    keywords = models.CharField(max_length=200, blank=True, help_text="Comma-separated keywords")

    def __str__(self):
        return self.title

class GuidelineSchedule(models.Model):
    DOW = [
        (0,"Monday"), (1,"Tuesday"), (2,"Wednesday"),
        (3,"Thursday"), (4,"Friday"), (5,"Saturday"), (6,"Sunday")
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="guideline_schedule")
    day_of_week = models.IntegerField(choices=DOW)
    pillar = models.ForeignKey(GuidelinePillar, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("user","day_of_week")

    def __str__(self):
        return f"{self.get_day_of_week_display()} → {self.pillar or '—'}"


class ContentHeroImage(models.Model):
    content = models.ForeignKey('ContentItem', on_delete=models.CASCADE, related_name='hero_images')
    prompt = models.TextField()
    image_url = models.URLField()           # or use ImageField if you download to media
    provider = models.CharField(max_length=32, default='openai')
    size = models.CharField(max_length=16, default='1024x1024')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
