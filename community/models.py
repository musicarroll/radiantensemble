from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Visibility(models.TextChoices):
    PUBLIC = "public", "Public"
    MEMBERS = "members", "Members only"
    GROUPS = "groups", "Selected groups"
    PRIVATE = "private", "Private"


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class MemberProfile(TimestampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="member_profile")
    display_name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    photo = models.FileField(upload_to="member_photos/%Y/%m/", blank=True)
    bio = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    accent_color = models.CharField(max_length=24, default="#7c3aed")
    page_theme = models.CharField(max_length=40, default="radiant")
    custom_css = models.TextField(blank=True)
    page_is_public = models.BooleanField(default=False)

    class Meta:
        ordering = ["display_name"]

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.user.get_full_name() or self.user.username
        if not self.slug:
            self.slug = slugify(self.display_name) or self.user.username
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("member_page", kwargs={"slug": self.slug})

    def __str__(self):
        return self.display_name


class MemberProfileLink(TimestampedModel):
    profile = models.ForeignKey(MemberProfile, on_delete=models.CASCADE, related_name="links")
    title = models.CharField(max_length=160)
    url = models.URLField()
    description = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title


class VisibleContent(TimestampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.MEMBERS)
    visible_to_groups = models.ManyToManyField(Group, blank=True)
    visible_to_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="%(class)s_visible_items",
    )

    class Meta:
        abstract = True

    def is_visible_to(self, user):
        if self.visibility == Visibility.PUBLIC:
            return True
        if not user.is_authenticated:
            return False
        if user.is_staff or user == self.owner or self.visible_to_users.filter(pk=user.pk).exists():
            return True
        if self.visibility == Visibility.MEMBERS:
            return True
        if self.visibility == Visibility.GROUPS:
            return self.visible_to_groups.filter(pk__in=user.groups.values("pk")).exists()
        return False


class Post(VisibleContent):
    title = models.CharField(max_length=180, blank=True)
    body = models.TextField()
    pinned = models.BooleanField(default=False)

    class Meta:
        ordering = ["-pinned", "-created_at"]

    def __str__(self):
        return self.title or f"Post by {self.owner}"


class Artifact(VisibleContent):
    class ArtifactType(models.TextChoices):
        PDF = "pdf", "PDF"
        AUDIO = "audio", "Audio"
        IMAGE = "image", "Image"
        ARTWORK = "artwork", "Artwork"
        OTHER = "other", "Other"

    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    artifact_type = models.CharField(max_length=20, choices=ArtifactType.choices, default=ArtifactType.OTHER)
    file = models.FileField(upload_to="artifacts/%Y/%m/")
    tags = models.CharField(max_length=255, blank=True, help_text="Comma-separated tags")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class MessageThread(TimestampedModel):
    title = models.CharField(max_length=180, blank=True)
    is_group_thread = models.BooleanField(default=False)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="message_threads")
    owning_group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"Thread {self.pk}"


class Message(TimestampedModel):
    thread = models.ForeignKey(MessageThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    body = models.TextField()
    attachment = models.FileField(upload_to="messages/%Y/%m/", blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender}: {self.body[:40]}"


class ContactMessage(TimestampedModel):
    name = models.CharField(max_length=160)
    email = models.EmailField()
    subject = models.CharField(max_length=180)
    message = models.TextField()
    remote_addr = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    turnstile_success = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} from {self.name}"


class Event(TimestampedModel):
    class EventVisibility(models.TextChoices):
        PUBLIC = "public", "Public"
        MEMBERS = "members", "Members only"

    class RepeatRule(models.TextChoices):
        NONE = "none", "Does not repeat"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly on same day of month"
        MONTHLY_ORDINAL = "monthly_ordinal", "Monthly on same ordinal weekday"

    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=220, blank=True)
    event_date = models.DateField()
    event_time = models.TimeField()
    visibility = models.CharField(max_length=20, choices=EventVisibility.choices, default=EventVisibility.MEMBERS)
    repeat = models.CharField(max_length=20, choices=RepeatRule.choices, default=RepeatRule.NONE)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submitted_events")

    class Meta:
        ordering = ["event_date", "event_time", "title"]

    def is_visible_to(self, user):
        return self.visibility == self.EventVisibility.PUBLIC or user.is_authenticated

    def occurs_on(self, date_value):
        if date_value < self.event_date:
            return False
        if self.pk and EventCancellation.objects.filter(event=self, occurrence_date=date_value).exists():
            return False
        if self.repeat == self.RepeatRule.NONE:
            return date_value == self.event_date
        if self.repeat == self.RepeatRule.DAILY:
            return True
        if self.repeat == self.RepeatRule.WEEKLY:
            return (date_value - self.event_date).days % 7 == 0
        if self.repeat == self.RepeatRule.MONTHLY:
            return date_value.day == self.event_date.day
        if self.repeat == self.RepeatRule.MONTHLY_ORDINAL:
            event_ordinal = ((self.event_date.day - 1) // 7) + 1
            date_ordinal = ((date_value.day - 1) // 7) + 1
            return date_value.weekday() == self.event_date.weekday() and date_ordinal == event_ordinal
        return False

    def next_occurrence_on_or_after(self, date_value):
        if self.repeat == self.RepeatRule.NONE:
            return self.event_date if self.event_date >= date_value else None
        candidate = max(date_value, self.event_date)
        for offset in range(370):
            occurrence_date = candidate + timezone.timedelta(days=offset)
            if self.occurs_on(occurrence_date):
                return occurrence_date
        return None

    def __str__(self):
        return self.title


class EventCancellation(TimestampedModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="cancellations")
    occurrence_date = models.DateField()
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cancelled_event_occurrences")

    class Meta:
        ordering = ["event", "occurrence_date"]
        constraints = [
            models.UniqueConstraint(fields=["event", "occurrence_date"], name="unique_event_cancellation")
        ]

    def __str__(self):
        return f"{self.event} cancelled on {self.occurrence_date}"


class WorkItemStatus(models.TextChoices):
    NEW = "new", "New"
    REVIEWING = "reviewing", "Reviewing"
    PLANNED = "planned", "Planned"
    IN_PROGRESS = "in_progress", "In progress"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class BugSeverity(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class FeatureImpact(models.TextChoices):
    NICE_TO_HAVE = "nice_to_have", "Nice to have"
    USEFUL = "useful", "Useful"
    IMPORTANT = "important", "Important"
    ESSENTIAL = "essential", "Essential"


class BugReport(TimestampedModel):
    title = models.CharField(max_length=180)
    description = models.TextField()
    steps_to_reproduce = models.TextField(blank=True)
    expected_behavior = models.TextField(blank=True)
    actual_behavior = models.TextField(blank=True)
    page_url = models.URLField(blank=True)
    severity = models.CharField(max_length=20, choices=BugSeverity.choices, default=BugSeverity.MEDIUM)
    status = models.CharField(max_length=20, choices=WorkItemStatus.choices, default=WorkItemStatus.NEW)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bug_reports")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class FeatureRequest(TimestampedModel):
    title = models.CharField(max_length=180)
    description = models.TextField()
    use_case = models.TextField(blank=True)
    benefit = models.TextField(blank=True)
    impact = models.CharField(max_length=20, choices=FeatureImpact.choices, default=FeatureImpact.USEFUL)
    status = models.CharField(max_length=20, choices=WorkItemStatus.choices, default=WorkItemStatus.NEW)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="feature_requests")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

# Create your models here.
