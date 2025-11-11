from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User, Onboarding, Upload
from datetime import date

class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)
    class Meta:
        model = User
        fields = ("username","email","password1","password2")

class OnboardingForm(forms.ModelForm):
    class Meta:
        model = Onboarding
        
        fields = ("industry","writing_style_keywords","goals","topical_keywords","bio","style_self_desc")
        widgets = {
            "writing_style_keywords": forms.TextInput(attrs={"placeholder":"e.g., witty, concise, data-led"}),
            "goals": forms.Textarea(attrs={"rows":3, "placeholder":"What do you want from the content?"}),
            "industry": forms.TextInput(attrs={"placeholder":"e.g., D2C fashion, SaaS CX"}),
            "topical_keywords": forms.Textarea(attrs={"rows":2, "placeholder":"e.g. CX, D2C, WhatsApp, product teardown"}),
            "bio": forms.Textarea(attrs={"rows":2, "placeholder":"One paragraph about you/brand"}),
            "style_self_desc": forms.Textarea(attrs={"rows":2, "placeholder":"Optional: how *you* describe your style"}),
        }

class UploadForm(forms.ModelForm):
    class Meta:
        model = Upload
        fields = ("file",)

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = f.name.lower()
        if not (name.endswith(".txt") or name.endswith(".pdf")):
            raise forms.ValidationError("Only .txt or .pdf files are allowed.")
        if f.size > 25 * 1024 * 1024:
            raise forms.ValidationError("Max file size is 25 MB.")
        return f

class GenerateContentForm(forms.Form):
    TYPE_CHOICES = [("BLOG","Blog"), ("LINKEDIN","LinkedIn")]
    type = forms.ChoiceField(choices=TYPE_CHOICES)
    topic = forms.CharField(max_length=200, widget=forms.TextInput(attrs={"placeholder":"e.g., WhatsApp is the new homepage for D2C"}))
    target_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"]
    )

class ApproveForm(forms.Form):
    confirm = forms.BooleanField(required=True, initial=True, label="Confirm approval")

class ImproveForm(forms.Form):
    LENGTH_CHOICES = [("short","Short"), ("medium","Medium"), ("long","Long")]
    TONE_CHOICES = [("as_is","As is"), ("casual","More casual"), ("formal","More formal")]

    length = forms.ChoiceField(choices=LENGTH_CHOICES, initial="medium")
    tone = forms.ChoiceField(choices=TONE_CHOICES, initial="as_is")
    add_example = forms.BooleanField(required=False, initial=False, label="Add an example")
    add_data = forms.BooleanField(required=False, initial=False, label="Add a data point")
    custom_note = forms.CharField(required=False, max_length=300, widget=forms.TextInput(attrs={"placeholder":"Optional nudge (max 300 chars)"}))

class ChangeTopicForm(forms.Form):
    new_topic = forms.CharField(max_length=200, widget=forms.TextInput(attrs={"placeholder":"New topic/title"}))


class AutoPopulateForm(forms.Form):
    TYPE_CHOICES = [("BLOG","Blog"), ("LINKEDIN","LinkedIn")]
    content_type = forms.ChoiceField(choices=TYPE_CHOICES)
    dates = forms.CharField(widget=forms.Textarea(attrs={
        "rows":3, "placeholder":"Enter up to 7 dates (YYYY-MM-DD), one per line"
    }))

class TypedPostForm(forms.Form):
    text = forms.CharField(
        widget=forms.Textarea(attrs={"class":"form-control", "rows":4, "placeholder":"Paste or type your latest post…"}),
        max_length=20000
    )
