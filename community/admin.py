from django.contrib import admin

from .models import (
    Artifact,
    BugReport,
    ContactMessage,
    Event,
    EventCancellation,
    FeatureRequest,
    MemberProfile,
    Message,
    MessageThread,
    Post,
)


@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "page_is_public", "page_theme", "updated_at")
    prepopulated_fields = {"slug": ("display_name",)}
    search_fields = ("display_name", "user__username", "bio")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "visibility", "pinned", "created_at")
    list_filter = ("visibility", "pinned", "created_at")
    search_fields = ("title", "body", "owner__username")
    filter_horizontal = ("visible_to_groups", "visible_to_users")


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    list_display = ("title", "artifact_type", "owner", "visibility", "created_at")
    list_filter = ("artifact_type", "visibility", "created_at")
    search_fields = ("title", "description", "tags", "owner__username")
    filter_horizontal = ("visible_to_groups", "visible_to_users")


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0


@admin.register(MessageThread)
class MessageThreadAdmin(admin.ModelAdmin):
    list_display = ("title", "is_group_thread", "owning_group", "updated_at")
    filter_horizontal = ("participants",)
    inlines = [MessageInline]


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "turnstile_success", "created_at")
    list_filter = ("turnstile_success", "created_at")
    search_fields = ("name", "email", "subject", "message")
    readonly_fields = ("created_at", "updated_at", "remote_addr", "user_agent", "turnstile_success")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_date", "event_time", "visibility", "repeat", "submitted_by")
    list_filter = ("visibility", "repeat", "event_date")
    search_fields = ("title", "description", "location", "submitted_by__username")


@admin.register(EventCancellation)
class EventCancellationAdmin(admin.ModelAdmin):
    list_display = ("event", "occurrence_date", "cancelled_by", "created_at")
    list_filter = ("occurrence_date", "created_at")
    search_fields = ("event__title", "cancelled_by__username")


@admin.register(BugReport)
class BugReportAdmin(admin.ModelAdmin):
    list_display = ("title", "severity", "status", "submitted_by", "created_at")
    list_filter = ("severity", "status", "created_at")
    search_fields = ("title", "description", "submitted_by__username")


@admin.register(FeatureRequest)
class FeatureRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "impact", "status", "submitted_by", "created_at")
    list_filter = ("impact", "status", "created_at")
    search_fields = ("title", "description", "submitted_by__username")

# Register your models here.
