from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from datetime import date, time

from .models import ContactMessage, Event, EventCancellation, MessageThread, Post, Visibility


class VisibilityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="testpass")
        self.member = User.objects.create_user(username="member", password="testpass")
        self.group = Group.objects.create(name="Sopranos")

    def test_public_post_visible_to_anonymous_user(self):
        post = Post.objects.create(owner=self.owner, body="Public note", visibility=Visibility.PUBLIC)
        self.assertTrue(post.is_visible_to(self.client.request().wsgi_request.user))

    def test_members_only_post_hidden_from_anonymous_user(self):
        post = Post.objects.create(owner=self.owner, body="Members note", visibility=Visibility.MEMBERS)
        self.assertFalse(post.is_visible_to(self.client.request().wsgi_request.user))

    def test_group_post_visible_to_group_member(self):
        self.member.groups.add(self.group)
        post = Post.objects.create(owner=self.owner, body="Section note", visibility=Visibility.GROUPS)
        post.visible_to_groups.add(self.group)
        self.assertTrue(post.is_visible_to(self.member))


class PublicPageTests(TestCase):
    def test_anonymous_home_redirects_to_about(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, reverse("about"))

    def test_authenticated_home_loads_member_dashboard(self):
        User.objects.create_user(username="member", password="testpass")
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "radiant-home")

    def test_about_page_loads(self):
        response = self.client.get(reverse("about"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Radiant Ensemble")

    @override_settings(CF_TURNSTILE_ENABLED=False)
    def test_contact_form_saves_when_turnstile_disabled(self):
        response = self.client.post(
            reverse("contact"),
            {
                "name": "Visitor",
                "email": "visitor@example.com",
                "subject": "Booking question",
                "message": "Hello from the public site.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message Sent")
        self.assertEqual(ContactMessage.objects.count(), 1)

    @override_settings(CF_TURNSTILE_ENABLED=True, CF_TURNSTILE_SECRET_KEY="")
    def test_contact_form_requires_turnstile_configuration_when_enabled(self):
        response = self.client.post(
            reverse("contact"),
            {
                "name": "Visitor",
                "email": "visitor@example.com",
                "subject": "Booking question",
                "message": "Hello from the public site.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contact verification is not configured yet.")
        self.assertEqual(ContactMessage.objects.count(), 0)


class EventTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="member", password="testpass")

    def test_calendar_requires_login(self):
        response = self.client.get(reverse("calendar"))
        self.assertEqual(response.status_code, 302)

    def test_member_can_add_event(self):
        self.client.login(username="member", password="testpass")
        response = self.client.post(
            reverse("add_event"),
            {
                "title": "Rehearsal",
                "description": "Full ensemble",
                "location": "Studio A",
                "event_date": "2026-07-10",
                "event_time": "19:30",
                "visibility": Event.EventVisibility.MEMBERS,
                "repeat": Event.RepeatRule.NONE,
            },
        )
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title="Rehearsal")
        self.assertEqual(event.submitted_by, self.member)

    def test_upcoming_events_lists_public_future_events(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Concert",
            description="Public concert",
            location="Main Hall",
            event_date=timezone.localdate() + timezone.timedelta(days=3),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.PUBLIC,
        )
        response = self.client.get(reverse("upcoming_events"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Concert")

    def test_upcoming_events_hides_member_only_events(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Private Rehearsal",
            event_date=timezone.localdate() + timezone.timedelta(days=3),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        response = self.client.get(reverse("upcoming_events"))
        self.assertNotContains(response, "Private Rehearsal")

    def test_event_detail_hides_member_only_event_from_anonymous_user(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Members Only",
            event_date=timezone.localdate(),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        response = self.client.get(reverse("event_detail", kwargs={"event_id": event.pk}))
        self.assertEqual(response.status_code, 404)

    def test_calendar_shows_weekly_recurring_event_in_month(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Weekly Sectional",
            event_date=date(2026, 7, 1),
            event_time=time(18, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.WEEKLY,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("calendar"), {"year": 2026, "month": 7})
        self.assertContains(response, "Weekly Sectional", count=5)

    def test_public_recurring_event_appears_on_upcoming_page(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Daily Warmup",
            event_date=timezone.localdate() - timezone.timedelta(days=1),
            event_time=time(9, 0),
            visibility=Event.EventVisibility.PUBLIC,
            repeat=Event.RepeatRule.DAILY,
        )
        response = self.client.get(reverse("upcoming_events"))
        self.assertContains(response, "Daily Warmup")

    def test_monthly_ordinal_event_matches_same_ordinal_weekday(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Second Tuesday Planning",
            event_date=date(2026, 7, 14),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.MONTHLY_ORDINAL,
        )
        self.assertTrue(event.occurs_on(date(2026, 8, 11)))
        self.assertFalse(event.occurs_on(date(2026, 8, 14)))

    def test_calendar_shows_monthly_ordinal_event_in_later_month(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Second Tuesday Planning",
            event_date=date(2026, 7, 14),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.MONTHLY_ORDINAL,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("calendar"), {"year": 2026, "month": 8})
        self.assertContains(response, "Second Tuesday Planning", count=1)
        self.assertContains(response, "date=2026-08-11")

    def test_public_monthly_ordinal_event_appears_on_upcoming_page(self):
        Event.objects.create(
            submitted_by=self.member,
            title="Monthly Public Jam",
            event_date=timezone.localdate() - timezone.timedelta(days=35),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.PUBLIC,
            repeat=Event.RepeatRule.MONTHLY_ORDINAL,
        )
        response = self.client.get(reverse("upcoming_events"))
        self.assertContains(response, "Monthly Public Jam")

    def test_event_creator_can_edit_event(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Original Event",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.post(
            reverse("edit_event", kwargs={"event_id": event.pk}),
            {
                "title": "Updated Event",
                "description": "Updated",
                "location": "New Room",
                "event_date": "2026-07-11",
                "event_time": "20:00",
                "visibility": Event.EventVisibility.PUBLIC,
                "repeat": Event.RepeatRule.WEEKLY,
            },
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.title, "Updated Event")
        self.assertEqual(event.submitted_by, self.member)

    def test_staff_can_edit_someone_elses_event(self):
        staff = User.objects.create_user(username="staff-event", password="testpass", is_staff=True)
        event = Event.objects.create(
            submitted_by=self.member,
            title="Member Event",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="staff-event", password="testpass")
        response = self.client.post(
            reverse("edit_event", kwargs={"event_id": event.pk}),
            {
                "title": "Staff Updated Event",
                "description": "",
                "location": "",
                "event_date": "2026-07-10",
                "event_time": "19:00",
                "visibility": Event.EventVisibility.PUBLIC,
                "repeat": Event.RepeatRule.NONE,
            },
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.title, "Staff Updated Event")
        self.assertEqual(event.submitted_by, self.member)

    def test_non_creator_cannot_edit_event(self):
        other = User.objects.create_user(username="other-event", password="testpass")
        event = Event.objects.create(
            submitted_by=self.member,
            title="Member Event",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="other-event", password="testpass")
        response = self.client.get(reverse("edit_event", kwargs={"event_id": event.pk}))
        self.assertEqual(response.status_code, 404)

    def test_event_creator_can_delete_event(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Delete Me",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.post(reverse("delete_event", kwargs={"event_id": event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_staff_can_delete_someone_elses_event(self):
        staff = User.objects.create_user(username="staff-delete-event", password="testpass", is_staff=True)
        event = Event.objects.create(
            submitted_by=self.member,
            title="Delete By Staff",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="staff-delete-event", password="testpass")
        response = self.client.post(reverse("delete_event", kwargs={"event_id": event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_non_creator_cannot_delete_event(self):
        other = User.objects.create_user(username="other-delete-event", password="testpass")
        event = Event.objects.create(
            submitted_by=self.member,
            title="Keep Me",
            event_date=date(2026, 7, 10),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
        )
        self.client.login(username="other-delete-event", password="testpass")
        response = self.client.post(reverse("delete_event", kwargs={"event_id": event.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_creator_can_delete_single_repeated_occurrence(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Weekly Rehearsal",
            event_date=date(2026, 7, 1),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.WEEKLY,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.post(
            reverse("delete_event_occurrence", kwargs={"event_id": event.pk}),
            {"occurrence_date": "2026-07-08"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())
        self.assertTrue(EventCancellation.objects.filter(event=event, occurrence_date=date(2026, 7, 8)).exists())
        self.assertFalse(event.occurs_on(date(2026, 7, 8)))
        self.assertTrue(event.occurs_on(date(2026, 7, 15)))

    def test_cancelled_occurrence_hidden_from_calendar(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="Weekly Rehearsal",
            event_date=date(2026, 7, 1),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.WEEKLY,
        )
        EventCancellation.objects.create(event=event, occurrence_date=date(2026, 7, 8), cancelled_by=self.member)
        self.client.login(username="member", password="testpass")
        response = self.client.get(reverse("calendar"), {"year": 2026, "month": 7})
        self.assertContains(response, "Weekly Rehearsal", count=4)
        self.assertNotContains(response, "date=2026-07-08")

    def test_staff_can_delete_someone_elses_single_occurrence(self):
        staff = User.objects.create_user(username="staff-cancel-event", password="testpass", is_staff=True)
        event = Event.objects.create(
            submitted_by=self.member,
            title="Weekly Rehearsal",
            event_date=date(2026, 7, 1),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.WEEKLY,
        )
        self.client.login(username="staff-cancel-event", password="testpass")
        response = self.client.post(
            reverse("delete_event_occurrence", kwargs={"event_id": event.pk}),
            {"occurrence_date": "2026-07-08"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EventCancellation.objects.filter(event=event, occurrence_date=date(2026, 7, 8)).exists())

    def test_non_creator_cannot_delete_single_occurrence(self):
        other = User.objects.create_user(username="other-cancel-event", password="testpass")
        event = Event.objects.create(
            submitted_by=self.member,
            title="Weekly Rehearsal",
            event_date=date(2026, 7, 1),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.WEEKLY,
        )
        self.client.login(username="other-cancel-event", password="testpass")
        response = self.client.post(
            reverse("delete_event_occurrence", kwargs={"event_id": event.pk}),
            {"occurrence_date": "2026-07-08"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(EventCancellation.objects.filter(event=event, occurrence_date=date(2026, 7, 8)).exists())

    def test_single_occurrence_delete_removes_one_time_event(self):
        event = Event.objects.create(
            submitted_by=self.member,
            title="One Time Concert",
            event_date=date(2026, 7, 1),
            event_time=time(19, 0),
            visibility=Event.EventVisibility.MEMBERS,
            repeat=Event.RepeatRule.NONE,
        )
        self.client.login(username="member", password="testpass")
        response = self.client.post(
            reverse("delete_event_occurrence", kwargs={"event_id": event.pk}),
            {"occurrence_date": "2026-07-01"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())


class ApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="testpass")
        Post.objects.create(owner=self.owner, title="Hello", body="Members", visibility=Visibility.MEMBERS)
        Post.objects.create(owner=self.owner, title="Public", body="Everyone", visibility=Visibility.PUBLIC)

    def test_home_feed_only_returns_public_posts_for_anonymous_user(self):
        response = self.client.get(reverse("api_home_feed"))
        self.assertEqual(response.status_code, 200)
        titles = [post["title"] for post in response.json()["posts"]]
        self.assertEqual(titles, ["Public"])

    def test_home_feed_returns_member_posts_for_logged_in_user(self):
        self.client.login(username="owner", password="testpass")
        response = self.client.get(reverse("api_home_feed"))
        titles = [post["title"] for post in response.json()["posts"]]
        self.assertIn("Hello", titles)

    def test_staff_can_create_pinned_post(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("create_post"),
            {"title": "Pinned", "body": "Stay on top", "visibility": Visibility.MEMBERS, "pinned": "true"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Post.objects.get(title="Pinned").pinned)

    def test_non_staff_cannot_create_pinned_post(self):
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("create_post"),
            {"title": "Not pinned", "body": "Regular post", "visibility": Visibility.MEMBERS, "pinned": "true"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(Post.objects.get(title="Not pinned").pinned)

    def test_pinned_posts_sort_above_regular_posts_with_latest_pinned_first(self):
        first = Post.objects.create(owner=self.owner, title="First pinned", body="One", visibility=Visibility.PUBLIC, pinned=True)
        second = Post.objects.create(owner=self.owner, title="Second pinned", body="Two", visibility=Visibility.PUBLIC, pinned=True)
        regular = Post.objects.create(owner=self.owner, title="Regular", body="Three", visibility=Visibility.PUBLIC)
        Post.objects.filter(pk=first.pk).update(created_at=timezone.now() - timezone.timedelta(days=2))
        Post.objects.filter(pk=second.pk).update(created_at=timezone.now() - timezone.timedelta(days=1))
        Post.objects.filter(pk=regular.pk).update(created_at=timezone.now())
        response = self.client.get(reverse("api_home_feed"))
        titles = [post["title"] for post in response.json()["posts"][:3]]
        self.assertEqual(titles, ["Second pinned", "First pinned", "Regular"])

    def test_owner_can_update_own_post(self):
        post = Post.objects.get(title="Hello")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("update_post", kwargs={"post_id": post.pk}),
            {"title": "Updated", "body": "Revised body", "visibility": Visibility.PUBLIC},
        )
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertEqual(post.title, "Updated")
        self.assertEqual(post.body, "Revised body")
        self.assertEqual(post.visibility, Visibility.PUBLIC)

    def test_staff_owner_can_update_pinned_state(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        post = Post.objects.get(title="Hello")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("update_post", kwargs={"post_id": post.pk}),
            {"title": "Hello", "body": "Members", "visibility": Visibility.MEMBERS, "pinned": "true"},
        )
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertTrue(post.pinned)

    def test_non_staff_owner_cannot_update_pinned_state(self):
        post = Post.objects.get(title="Hello")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("update_post", kwargs={"post_id": post.pk}),
            {"title": "Hello", "body": "Members", "visibility": Visibility.MEMBERS, "pinned": "true"},
        )
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertFalse(post.pinned)

    def test_staff_can_pin_someone_elses_post(self):
        staff = User.objects.create_user(username="staff", password="testpass", is_staff=True)
        post = Post.objects.get(title="Hello")
        self.client.login(username="staff", password="testpass")
        response = self.client.post(reverse("pin_post", kwargs={"post_id": post.pk}), {"pinned": "true"})
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertTrue(post.pinned)

    def test_staff_can_unpin_someone_elses_post(self):
        staff = User.objects.create_user(username="staff", password="testpass", is_staff=True)
        post = Post.objects.get(title="Hello")
        post.pinned = True
        post.save(update_fields=["pinned"])
        self.client.login(username="staff", password="testpass")
        response = self.client.post(reverse("pin_post", kwargs={"post_id": post.pk}), {"pinned": "false"})
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertFalse(post.pinned)

    def test_non_staff_cannot_pin_someone_elses_post(self):
        other = User.objects.create_user(username="other-pin", password="testpass")
        post = Post.objects.get(title="Hello")
        self.client.login(username="other-pin", password="testpass")
        response = self.client.post(reverse("pin_post", kwargs={"post_id": post.pk}), {"pinned": "true"})
        self.assertEqual(response.status_code, 403)
        post.refresh_from_db()
        self.assertFalse(post.pinned)

    def test_non_owner_cannot_update_post(self):
        other = User.objects.create_user(username="other", password="testpass")
        post = Post.objects.get(title="Hello")
        self.client.login(username="other", password="testpass")
        response = self.client.post(
            reverse("update_post", kwargs={"post_id": post.pk}),
            {"title": "Bad edit", "body": "Nope", "visibility": Visibility.MEMBERS},
        )
        self.assertEqual(response.status_code, 403)
        post.refresh_from_db()
        self.assertEqual(post.title, "Hello")

    def test_update_post_requires_body(self):
        post = Post.objects.get(title="Hello")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("update_post", kwargs={"post_id": post.pk}),
            {"title": "Updated", "body": "", "visibility": Visibility.MEMBERS},
        )
        self.assertEqual(response.status_code, 400)

    def test_owner_can_delete_own_post(self):
        post = Post.objects.get(title="Hello")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(reverse("delete_post", kwargs={"post_id": post.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())

    def test_non_owner_cannot_delete_post(self):
        other = User.objects.create_user(username="other-delete", password="testpass")
        post = Post.objects.get(title="Hello")
        self.client.login(username="other-delete", password="testpass")
        response = self.client.post(reverse("delete_post", kwargs={"post_id": post.pk}))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Post.objects.filter(pk=post.pk).exists())

    def test_artifact_upload_requires_file(self):
        self.client.login(username="owner", password="testpass")
        response = self.client.post(reverse("upload_artifact"), {"title": "Score"})
        self.assertEqual(response.status_code, 400)

    def test_create_direct_thread_requires_login(self):
        response = self.client.post(reverse("create_direct_thread"), {"recipient_id": self.owner.pk, "body": "Hello"})
        self.assertEqual(response.status_code, 302)

    def test_create_direct_thread_with_initial_message(self):
        recipient = User.objects.create_user(username="recipient", password="testpass")
        self.client.login(username="owner", password="testpass")
        response = self.client.post(
            reverse("create_direct_thread"),
            {"recipient_id": recipient.pk, "body": "Can you rehearse tonight?"},
        )
        self.assertEqual(response.status_code, 201)
        thread = MessageThread.objects.get(pk=response.json()["thread"]["id"])
        self.assertEqual(thread.participants.count(), 2)
        self.assertEqual(thread.messages.count(), 1)

    def test_thread_detail_limited_to_participants(self):
        recipient = User.objects.create_user(username="recipient", password="testpass")
        outsider = User.objects.create_user(username="outsider", password="testpass")
        thread = MessageThread.objects.create()
        thread.participants.add(self.owner, recipient)
        self.client.login(username="outsider", password="testpass")
        response = self.client.get(reverse("api_thread_detail", kwargs={"thread_id": thread.pk}))
        self.assertEqual(response.status_code, 404)

    def test_thread_page_limited_to_participants(self):
        recipient = User.objects.create_user(username="recipient", password="testpass")
        outsider = User.objects.create_user(username="outsider", password="testpass")
        thread = MessageThread.objects.create()
        thread.participants.add(self.owner, recipient)
        self.client.login(username="outsider", password="testpass")
        response = self.client.get(reverse("thread_page", kwargs={"thread_id": thread.pk}))
        self.assertEqual(response.status_code, 404)

    def test_thread_page_visible_to_participant(self):
        recipient = User.objects.create_user(username="recipient", password="testpass")
        thread = MessageThread.objects.create()
        thread.participants.add(self.owner, recipient)
        self.client.login(username="owner", password="testpass")
        response = self.client.get(reverse("thread_page", kwargs={"thread_id": thread.pk}))
        self.assertEqual(response.status_code, 200)

    def test_send_message_to_thread(self):
        recipient = User.objects.create_user(username="recipient", password="testpass")
        thread = MessageThread.objects.create()
        thread.participants.add(self.owner, recipient)
        self.client.login(username="owner", password="testpass")
        response = self.client.post(reverse("send_message", kwargs={"thread_id": thread.pk}), {"body": "Marked the bowings."})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(thread.messages.count(), 1)
