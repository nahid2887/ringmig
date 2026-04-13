from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import ListenerAvailability, TimeSlot, UniversalBookingPackage, SessionBooking

User = get_user_model()


class TimeSlotSerializer(serializers.ModelSerializer):
    """Serializer for individual time slots."""
    day_of_week_display = serializers.CharField(
        source='get_day_of_week_display',
        read_only=True
    )
    duration_minutes = serializers.SerializerMethodField()

    class Meta:
        model = TimeSlot
        fields = ['id', 'day_of_week', 'day_of_week_display', 'start_time', 'end_time', 'duration_minutes']
        read_only_fields = ['id', 'duration_minutes']

    def get_duration_minutes(self, obj):
        """Get the duration of the time slot."""
        return obj.duration_minutes()


class ListenerAvailabilityDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for Listener Availability with nested time slots."""
    time_slots = TimeSlotSerializer(many=True, read_only=True)
    listener_email = serializers.CharField(
        source='listener.email',
        read_only=True
    )

    class Meta:
        model = ListenerAvailability
        fields = ['id', 'listener_email', 'buffer_time_minutes', 'time_slots', 'created_at', 'updated_at']
        read_only_fields = ['id', 'listener_email', 'created_at', 'updated_at']


class TimeSlotInputSerializer(serializers.Serializer):
    """Serializer for time slot input in availability creation/update."""
    day_of_week = serializers.IntegerField(
        help_text="Day of week (0=Monday, 6=Sunday)"
    )
    start_time = serializers.TimeField(format='%H:%M')
    end_time = serializers.TimeField(format='%H:%M')

    def validate(self, data):
        """Validate that start_time is before end_time."""
        if data['start_time'] >= data['end_time']:
            raise serializers.ValidationError("Start time must be before end time")
        if not (0 <= data['day_of_week'] <= 6):
            raise serializers.ValidationError("Day of week must be between 0 (Monday) and 6 (Sunday)")
        return data


class ListenerAvailabilityCreateUpdateSerializer(serializers.Serializer):
    """Serializer for creating/updating listener availability with multiple time slots."""
    buffer_time_minutes = serializers.IntegerField(
        required=False,
        default=5,
        min_value=0,
        help_text="Buffer time in minutes between consecutive sessions"
    )
    time_slots = TimeSlotInputSerializer(
        many=True,
        help_text="List of time slots for the week"
    )

    def validate_time_slots(self, value):
        """Validate that time slots list is not empty."""
        if not value:
            raise serializers.ValidationError("At least one time slot must be provided")
        return value

    def create(self, validated_data):
        """Create availability with time slots."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = self.context['request'].user
        buffer_time = validated_data['buffer_time_minutes']
        time_slots_data = validated_data['time_slots']

        # Create or update ListenerAvailability
        availability, created = ListenerAvailability.objects.update_or_create(
            listener=user,
            defaults={'buffer_time_minutes': buffer_time}
        )

        # Clear existing time slots
        availability.time_slots.all().delete()

        # Create new time slots
        for slot_data in time_slots_data:
            TimeSlot.objects.create(
                availability=availability,
                day_of_week=slot_data['day_of_week'],
                start_time=slot_data['start_time'],
                end_time=slot_data['end_time']
            )

        return availability

    def update(self, instance, validated_data):
        """Update availability with time slots."""
        # Update buffer time if provided
        if 'buffer_time_minutes' in validated_data:
            instance.buffer_time_minutes = validated_data['buffer_time_minutes']
            instance.save()

        # Handle time slots if provided
        if 'time_slots' in validated_data:
            time_slots_data = validated_data['time_slots']
            instance.time_slots.all().delete()

            for slot_data in time_slots_data:
                TimeSlot.objects.create(
                    availability=instance,
                    day_of_week=slot_data['day_of_week'],
                    start_time=slot_data['start_time'],
                    end_time=slot_data['end_time']
                )

        return instance


class BufferTimeUpdateSerializer(serializers.Serializer):
    """Serializer for updating just the buffer time."""
    buffer_time_minutes = serializers.IntegerField(
        min_value=0,
        help_text="Buffer time in minutes between consecutive sessions"
    )

    def update(self, instance, validated_data):
        """Update buffer time only."""
        instance.buffer_time_minutes = validated_data['buffer_time_minutes']
        instance.save()
        return instance


class UniversalBookingPackageSerializer(serializers.ModelSerializer):
    """Serializer for universal booking packages (admin-managed)."""

    app_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    listener_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = UniversalBookingPackage
        fields = [
            'id', 'name', 'description', 'package_type', 'media_type', 'duration',
            'price', 'app_fee_percentage', 'app_fee', 'listener_amount',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'app_fee', 'listener_amount']


class SessionBookingSerializer(serializers.ModelSerializer):
    """Serializer for session booking records."""

    talker_email = serializers.EmailField(source='talker.email', read_only=True)
    talker_name = serializers.SerializerMethodField()
    listener_email = serializers.EmailField(source='listener.email', read_only=True)
    listener_name = serializers.SerializerMethodField()
    package_details = UniversalBookingPackageSerializer(source='package', read_only=True)

    class Meta:
        model = SessionBooking
        fields = [
            'id', 'talker', 'talker_name', 'talker_email', 'listener', 'listener_name', 'listener_email',
            'package', 'package_details', 'booking_date', 'start_time', 'end_time',
            'duration_minutes', 'buffer_time_minutes', 'status', 'payment_link',
            'transaction_id', 'price', 'app_fee', 'listener_amount',
            'created_at', 'updated_at', 'payment_completed_at'
        ]
        read_only_fields = [
            'id', 'talker', 'talker_name', 'talker_email', 'listener_name', 'listener_email', 'end_time',
            'duration_minutes', 'buffer_time_minutes', 'status', 'payment_link',
            'transaction_id', 'price', 'app_fee', 'listener_amount',
            'created_at', 'updated_at', 'payment_completed_at'
        ]

    def get_talker_name(self, obj):
        return obj.talker.full_name or obj.talker.email

    def get_listener_name(self, obj):
        return obj.listener.full_name or obj.listener.email


class PurchaseSessionBookingSerializer(serializers.Serializer):
    """Input serializer for booking purchase flow."""

    listener_id = serializers.IntegerField()
    booking_package_id = serializers.IntegerField()
    booking_date = serializers.DateField()
    start_time = serializers.TimeField(format='%H:%M')
    payment_method_id = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text='Optional Stripe payment method id. Leave empty to receive checkout payment_link.'
    )

    def validate_listener_id(self, value):
        try:
            User.objects.get(id=value, user_type='listener', is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError('Listener not found')
        return value

    def validate_booking_package_id(self, value):
        try:
            UniversalBookingPackage.objects.get(id=value, is_active=True)
        except UniversalBookingPackage.DoesNotExist:
            raise serializers.ValidationError('Booking package not found or inactive')
        return value

    def validate(self, attrs):
        payment_method_id = attrs.get('payment_method_id')
        if payment_method_id in ['', None, 'string', 'null']:
            attrs.pop('payment_method_id', None)

        listener = User.objects.get(id=attrs['listener_id'])
        package = UniversalBookingPackage.objects.get(id=attrs['booking_package_id'])

        is_available, end_time, message = SessionBooking.check_slot_available(
            listener=listener,
            booking_date=attrs['booking_date'],
            start_time=attrs['start_time'],
            duration_minutes=package.duration
        )

        if not is_available:
            raise serializers.ValidationError({'slot': message})

        attrs['listener'] = listener
        attrs['package'] = package
        attrs['end_time'] = end_time
        return attrs


class ConfirmSessionBookingPaymentSerializer(serializers.Serializer):
    """Input serializer for explicit payment confirmation endpoint."""

    booking_id = serializers.UUIDField()
    payment_intent_id = serializers.CharField()


class RejectSessionBookingSerializer(serializers.Serializer):
    """Input serializer for listener booking rejection."""

    booking_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=255)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
