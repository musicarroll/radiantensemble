from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.forms import inlineformset_factory

from .models import Artifact, BugReport, ContactMessage, Event, FeatureRequest, MemberProfile, MemberProfileLink, Visibility


class PendingUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username"]


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "subject", "message"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 6}),
        }


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["title", "description", "location", "event_date", "event_time", "visibility", "repeat"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "event_date": forms.DateInput(attrs={"type": "date"}),
            "event_time": forms.TimeInput(attrs={"type": "time"}),
        }


class BugReportForm(forms.ModelForm):
    class Meta:
        model = BugReport
        fields = [
            "title",
            "description",
            "steps_to_reproduce",
            "expected_behavior",
            "actual_behavior",
            "page_url",
            "severity",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "steps_to_reproduce": forms.Textarea(attrs={"rows": 4}),
            "expected_behavior": forms.Textarea(attrs={"rows": 3}),
            "actual_behavior": forms.Textarea(attrs={"rows": 3}),
        }


class FeatureRequestForm(forms.ModelForm):
    class Meta:
        model = FeatureRequest
        fields = ["title", "description", "use_case", "benefit", "impact"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "use_case": forms.Textarea(attrs={"rows": 4}),
            "benefit": forms.Textarea(attrs={"rows": 3}),
        }


class MemberProfileForm(forms.ModelForm):
    class Meta:
        model = MemberProfile
        fields = ["display_name", "photo", "bio", "phone", "email", "accent_color"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 6}),
        }


MemberProfileLinkFormSet = inlineformset_factory(
    MemberProfile,
    MemberProfileLink,
    fields=["title", "url", "description", "sort_order"],
    extra=3,
    can_delete=True,
)


class ArtifactSearchForm(forms.Form):
    title = forms.CharField(required=False)
    description = forms.CharField(required=False)
    tags = forms.CharField(required=False)
    owner = forms.CharField(required=False, label="Owner username or ID")
    artifact_type = forms.ChoiceField(
        required=False,
        choices=[("", "Any")] + list(Artifact.ArtifactType.choices),
    )
    visibility = forms.ChoiceField(
        required=False,
        choices=[("", "Any")] + list(Visibility.choices),
    )
    created_after = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    created_before = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    updated_after = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    updated_before = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("placeholder", "Any")
