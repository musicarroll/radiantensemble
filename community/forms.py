from django import forms

from .models import BugReport, ContactMessage, Event, FeatureRequest


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
