from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

User = get_user_model()


class ListenerBlockedTalker(models.Model):
    """Model to track which talkers are blocked by listeners."""
    
    listener = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_talkers')
    talker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by_listeners')
    blocked_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('listener', 'talker')
        verbose_name = 'Listener Blocked Talker'
        verbose_name_plural = 'Listener Blocked Talkers'
        ordering = ['-blocked_at']
    
    def __str__(self):
        return f"{self.listener.email} blocked {self.talker.email}"


class ListenerProfile(models.Model):
    """Extended profile for listeners."""
    
    GENDER_CHOICES = [
        ('male', _('Male')),
        ('female', _('Female')),
        ('other', _('Other')),
        ('prefer_not_to_say', _('Prefer not to say')),
    ]
    
    EXPERIENCE_LEVEL = [
        ('beginner', _('Beginner')),
        ('intermediate', _('Intermediate')),
        ('advanced', _('Advanced')),
        ('expert', _('Expert')),
    ]
    
    TOPIC_CHOICES = [
        ('social_call', _('Social Call')),
        ('brainstorming', _('Brainstorming')),
        ('hobby', _('Hobby')),
        ('advice', _('Advice')),
        ('ask_dad', _('Ask Dad')),
        ('relationships', _('Relationships')),
        ('carrier', _('Carrier')),
        ('self_esteem', _('Self Esteem')),
        ('life_changes', _('Life Changes')),
        ('grief', _('Grief')),
        ('work_stress', _('Work Stress')),
        ('family', _('Family')),
        ('loneliness', _('Loneliness')),
        ('anxiety', _('Anxiety')),
        ('depression', _('Depression')),
    ]
    
    LANGUAGE_CHOICES = [
        ('en', _('English')),
        ('sv', _('Swedish')),
        ('es', _('Spanish')),
        ('fr', _('French')),
        ('de', _('German')),
        ('it', _('Italian')),
        ('pt', _('Portuguese')),
        ('ru', _('Russian')),
        ('ja', _('Japanese')),
        ('zh', _('Chinese')),
        ('ko', _('Korean')),
        ('ar', _('Arabic')),
        ('hi', _('Hindi')),
        ('nl', _('Dutch')),
        ('pl', _('Polish')),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='listener_profile')
    
    # Personal Information
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)
    profile_image = models.ImageField(upload_to='listener_profiles/', null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, help_text=_('City, Country'))
    
    # Professional Information
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_LEVEL, default='beginner')
    bio = models.TextField(blank=True, help_text=_('Tell talkers about yourself'))
    about_me = models.TextField(blank=True, help_text=_('Additional information about yourself'))
    specialties = models.JSONField(default=list, blank=True, help_text=_('List of listening specialties'))
    topics = models.JSONField(default=list, blank=True, help_text=_('Topics comfortable talking about'))
    languages = models.JSONField(default=list, blank=True, help_text=_('Languages the listener can speak'))
    
    # Availability & Pricing
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0, help_text=_('Rate per hour in USD'))
    is_available = models.BooleanField(default=True, help_text=_('Available for sessions'))
    accept_direct_calls = models.BooleanField(default=True, help_text=_('Accept direct calls from talkers'))
    
    # Statistics
    total_hours = models.IntegerField(default=0, help_text=_('Total listening hours'))
    average_rating = models.FloatField(default=0, help_text=_('Average rating from talkers'))
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Listener Profile'
        verbose_name_plural = 'Listener Profiles'

    def __str__(self):
        return f"Listener: {self.user.email}"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.user.email
    
    def update_average_rating(self):
        """Calculate and update average rating from all ratings."""
        ratings = self.ratings.all()
        if ratings.exists():
            avg = ratings.aggregate(models.Avg('rating'))['rating__avg']
            self.average_rating = round(avg, 2)
            self.save(update_fields=['average_rating'])


class ListenerRating(models.Model):
    """Rating given by a talker to a listener."""
    
    RATING_CHOICES = [
        (1, _('1 - Poor')),
        (2, _('2 - Fair')),
        (3, _('3 - Good')),
        (4, _('4 - Very Good')),
        (5, _('5 - Excellent')),
    ]
    
    listener = models.ForeignKey(ListenerProfile, on_delete=models.CASCADE, related_name='ratings')
    talker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listener_ratings')
    rating = models.IntegerField(choices=RATING_CHOICES)
    review = models.TextField(blank=True, help_text=_('Optional review comment'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Listener Rating'
        verbose_name_plural = 'Listener Ratings'
        unique_together = ['listener', 'talker']  # One rating per talker per listener

    def __str__(self):
        return f"{self.talker.email} rated {self.listener.user.email} - {self.rating}/5"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update the listener's average rating
        self.listener.update_average_rating()


class ListenerBalance(models.Model):
    """Single table to maintain listener's balance."""
    
    listener = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='balance_account',
        limit_choices_to={'user_type': 'listener'}
    )
    
    # Main balance field
    available_balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Current available balance')
    )
    
    # History tracking
    total_earned = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Total money earned (lifetime)')
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Listener Balance')
        verbose_name_plural = _('Listener Balances')
    
    def __str__(self):
        return f"{self.listener.email}: ${self.available_balance}"
    
    def add_earnings(self, amount):
        """Add money to balance."""
        amount = Decimal(str(amount))
        self.available_balance += amount
        self.total_earned += amount
        self.save(update_fields=['available_balance', 'total_earned', 'updated_at'])
    
    def deduct(self, amount):
        """Deduct money from balance (for future withdrawals)."""
        amount = Decimal(str(amount))
        if self.available_balance >= amount:
            self.available_balance -= amount
            self.save(update_fields=['available_balance', 'updated_at'])
            return True
        return False
