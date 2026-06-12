from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("skyhooker", "0004_skyhookerconfiguration"),
    ]

    operations = [
        migrations.AlterField(
            model_name="skyhookcorporation",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="skyhook",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="skyhooksnapshot",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="alertlog",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="alertresolution",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="skyhookerconfiguration",
            name="id",
            field=models.BigAutoField(primary_key=True, serialize=False),
        ),
    ]
