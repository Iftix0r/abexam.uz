from django.db import migrations

ROOMS = [
    ('umumiy', 'Umumiy suhbat', "Tanishing va fikr almashing", 'message-circle'),
    ('speaking', 'Speaking', "Mavzular va sherik topish", 'mic'),
    ('writing', 'Writing', "Essay va Task 1 bo'yicha maslahatlar", 'pen-line'),
    ('reading-listening', 'Reading va Listening', "Strategiya va tajriba", 'book-open'),
    ('savol-javob', 'Savol-javob', "Tushunmagan narsangizni so'rang", 'lightbulb'),
]


def add_rooms(apps, schema_editor):
    ChatRoom = apps.get_model('chat', 'ChatRoom')
    for order, (slug, title, description, icon) in enumerate(ROOMS):
        ChatRoom.objects.get_or_create(slug=slug, defaults={
            'title': title, 'description': description, 'icon': icon, 'order': order})


class Migration(migrations.Migration):
    dependencies = [('chat', '0001_initial')]
    operations = [migrations.RunPython(add_rooms, migrations.RunPython.noop)]
