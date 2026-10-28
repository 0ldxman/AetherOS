import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.db.models import Q

from filesystem.names import normalize_inner, validate_name
from secure.access import validate_requirements


class FileFormat(models.Model):
    """Формат файла: как выглядят его первые байты и устройство. Из этого строятся сырые байты файла (blk, txtx, вьювер raw)
    и ответы cvt. Игрок называет формат в cvt по имени.

    Виды устройства:
        signature  сигнатура (magic) и дальше тело как есть: обычные форматы (pdf, png...);
        text       текстовый шаблон с подстановками {body}, {who}...: форматы, которые читаются как текст;
        chunks     сигнатура и блоки «длина, метка, данные» (как PNG): части задаются ниже;
        package    сигнатура, число частей и таблица частей (имя, смещение, размер), затем сами части;
        zip        настоящий zip без сжатия: части это файлы внутри (docx, xlsx, epub...).
    """

    class Kind(models.TextChoices):
        SIGNATURE = "signature", "Сигнатура и тело"
        TEXT = "text", "Текстовый шаблон"
        CHUNKS = "chunks", "Блоки с метками"
        PACKAGE = "package", "Пакет частей с таблицей"
        ZIP = "zip", "Zip-контейнер (файлы внутри)"

    name = models.SlugField(
        max_length=32,
        unique=True,
        help_text="Как игрок называет формат в cvt: строчными буквами (scan, doc, pdf).",
    )
    title = models.CharField(max_length=128, blank=True, help_text="Подпись для админки и вьювера: SCAN картинка + OCR.")
    extension = models.CharField(max_length=16, blank=True, help_text="Расширение имени файла: .scan")
    aliases = models.CharField(
        max_length=128,
        blank=True,
        help_text="Другие расширения этого же формата через запятую: jpeg, jpe (у jpg). cvt и тип записи вики находят формат и по ним.",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.SIGNATURE)
    magic = models.TextField(
        blank=True,
        help_text="Первые байты в hex через пробел: 9e 53 43 41 4e 0d 0a 1b. Для текстового шаблона не нужны (сигнатура это начало шаблона).",
    )
    template = models.TextField(
        blank=True,
        help_text=(
            "Только для вида «текстовый шаблон». Подстановки: {body} текст, {body_html} текст абзацами HTML, {who}, {when}, "
            "{ref}, {src}, {at}, {title}, {hash}, {sender}, {recipients}, {subject}, {date}, {id}, {host} (имя узла); тело в других видах: {body_xml}, "
            "{body_json}, {body_csv}, {body_rtf}, {body_b64}. Фигурные скобки самого "
            "текста удваиваются: {{ }}."
        ),
    )

    class Content(models.TextChoices):
        TEXT = "text", "Текст"
        TEXT_ASSET = "text_asset", "Текст или ассет"
        ASSET = "asset", "Ассет"
        LINK_ASSET = "link_asset", "Ссылка или ассет"
        SCENE = "scene", "Сцена карты"
        MESSAGE = "message", "Письмо"
        NONE = "none", "Без содержимого"

    content = models.CharField(
        "Содержимое",
        max_length=16,
        choices=Content.choices,
        default=Content.TEXT_ASSET,
        help_text="Что вводится у объекта этого формата: текст, ассет из хранилища, ссылка, сцена карты, письмо или ничего.",
    )
    page = models.BooleanField(
        "Страница вики",
        default=False,
        help_text="Объект этого формата показывается в вики как страница.",
    )
    editable = models.BooleanField(
        "Можно править",
        default=False,
        help_text="Игрок может править файлы этого формата (edt). Выключено у форматов вроде PDF.",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Формат файла"
        verbose_name_plural = "Форматы файлов"

    def __str__(self):
        return self.name


class FormatPart(models.Model):
    """Часть формата с блоками или пакетом: имя (метка), откуда берётся её содержимое."""

    class Source(models.TextChoices):
        BODY = "body", "Текст источника (запись вики, письмо...)"
        IMAGE = "image", "Картинка источника (у ассета настоящая, иначе шум)"
        TEMPLATE = "template", "Текст-шаблон"
        HEX = "hex", "Постоянные байты (hex)"
        NOISE = "noise", "Шум (длина в значении)"
        CONFIDENCE = "confidence", "Байт уверенности (70-99)"

    format = models.ForeignKey(FileFormat, on_delete=models.CASCADE, related_name="parts")
    order = models.PositiveSmallIntegerField(default=0)
    name = models.CharField(
        max_length=64,
        help_text="Метка блока (ровно 4 символа), имя части пакета (до 8 символов) или путь файла внутри zip.",
    )
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.BODY)
    value = models.TextField(blank=True, help_text="Шаблон, hex-байты или длина шума; для остальных источников не нужно.")

    class Meta:
        ordering = ("format", "order", "id")
        verbose_name = "Часть формата"
        verbose_name_plural = "Части формата"

    def __str__(self):
        return f"{self.format.name}: {self.name}"


class FileEncoding(models.Model):
    """Кодировка слоя binary: во что завёрнут настоящий текст. Игрок называет её в cvt по имени."""

    class Kind(models.TextChoices):
        CODEC = "codec", "Кодек Python (utf-16-le, cp500...)"
        HEX = "hex", "Байты как hex-текст"
        ROT = "rot", "Сдвиг букв (rot13)"
        XOR = "xor", "XOR с байтом"
        GZIP = "gzip", "gzip"
        MORSE = "morse", "Азбука Морзе"
        REVERSE = "reverse", "Байты задом наперёд"
        BASE32 = "base32", "base32"
        ROT47 = "rot47", "rot47 (все печатные символы)"
        BIN = "bin", "Текст из нулей и единиц"
        DEC = "dec", "Коды символов десятичными числами"
        OCT = "oct", "Коды символов восьмеричными числами"
        URL = "url", "Процентная запись (%D0%9F)"
        BASE85 = "base85", "base85"
        UU = "uu", "uuencode"
        ATBASH = "atbash", "Атбаш (алфавит наоборот)"
        BASE64 = "base64", "base64 (параметры: url, nowrap)"

    name = models.SlugField(max_length=32, unique=True, help_text="Как игрок называет кодировку в cvt: utf16, rot13, morse.")
    title = models.CharField(max_length=128, blank=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    param = models.CharField(
        max_length=64,
        blank=True,
        help_text="codec: имя кодека; hex: разделитель (по умолчанию пробел); rot: сдвиг (13); xor: байт (0x5a или 90); base64: url (алфавит для URL, без «=»), nowrap (одной строкой).",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Кодировка слоя binary"
        verbose_name_plural = "Кодировки слоя binary"

    def __str__(self):
        return self.name



# ----------------------------------------------------------------------------------------------------------------------
# Тома и объекты (docs/storage-spec.md)
# ----------------------------------------------------------------------------------------------------------------------

KEY_FORMAT = "key"             # объект этого формата это ключ: его слаг входит в условия доступа
MAX_DEPTH = 16                 # самая глубокая вложенность папок в томе


REQUIRED_CONTENT = {"asset", "link_asset", "scene", "message"}       # этим форматам без содержимого делать нечего
ALLOWED_CONTENT = {                                                  # какие поля объекта использует формат (FileFormat.content)
    "text": {"body"},
    "text_asset": {"body", "asset"},
    "asset": {"asset"},
    "link_asset": {"url", "asset"},
    "scene": {"scene"},
    "message": {"message"},
    "none": set(),
}


class Item(models.Model):
    """Объект: любой файл сам по себе. Не привязан ни к тому, ни к машине: в том его кладёт Placement (так один объект лежит
    в нескольких томах без дубликатов).

    Что вводится в содержимое, зависит от формата (FileFormat.content): текст, ассет, ссылка, сцена карты, письмо.
    """

    slug = models.SlugField("Слаг", max_length=64, unique=True, help_text="Короткий идентификатор: латиница, цифры, «-» и «_».")
    name = models.CharField("Название", max_length=200, validators=[validate_name], help_text="Имя файла без расширения.")
    format = models.SlugField(
        "Формат", max_length=32, blank=True, help_text="Имя формата из реестра (scan, doc, key, conf...). Пусто: файл без формата.",
    )

    # содержимое
    body = models.TextField("Текст", blank=True)
    asset = models.ForeignKey(
        "assets.Asset", null=True, blank=True, on_delete=models.PROTECT, related_name="items", verbose_name="Ассет",
    )
    url = models.CharField(
        "Ссылка", max_length=2048, blank=True,
        validators=[URLValidator(schemes=["http", "https"])],
        help_text="Внешний адрес: окно его показывает, а байты файла генерируются.",
    )
    scene = models.ForeignKey(
        "map.MapScene", null=True, blank=True, on_delete=models.PROTECT, related_name="items", verbose_name="Сцена карты",
    )
    message = models.ForeignKey(
        "mail.Message", null=True, blank=True, on_delete=models.PROTECT, related_name="items", verbose_name="Письмо",
    )

    # доступ и внутренности
    access = models.JSONField(
        "Доступ", default=dict, blank=True, validators=[validate_requirements],
        help_text="Кому открыто содержимое: условие по слагам ключей. Пусто: всем.",
    )
    state = models.TextField("Слои защиты", blank=True)

    # метаданные
    size = models.PositiveBigIntegerField(
        "Размер", null=True, blank=True,
        help_text="Если не указан, считается по содержимому.",
    )
    meta = models.TextField("Метаинформация", blank=True, help_text="Свободный текст или разметка: дополнительное окно любого приложения.")
    world_created_at = models.DateField("Создан (в мире)", null=True, blank=True)
    world_updated_at = models.DateField("Изменён (в мире)", null=True, blank=True)
    world_creator = models.CharField("Автор (в мире)", max_length=128, blank=True)

    # админское
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        ordering = ("name", "slug")
        verbose_name = "Объект"
        verbose_name_plural = "Объекты"

    def __str__(self):
        return f"{self.name} [{self.slug}]"

    def file_format(self):
        """Запись реестра форматов этого объекта или None."""
        return FileFormat.objects.filter(name=self.format).first() if self.format else None

    @property
    def default_filename(self):
        """Имя файла по умолчанию: название и расширение формата."""
        found = self.file_format()
        return self.name + (found.extension if found else "")

    def clean(self):
        super().clean()
        found = self.file_format()
        if self.format and found is None:
            raise ValidationError({"format": "Такого формата нет в реестре."})

        used = {
            "body": bool(self.body.strip()),
            "asset": self.asset_id is not None,
            "url": bool(self.url),
            "scene": self.scene_id is not None,
            "message": self.message_id is not None,
        }
        allowed = ALLOWED_CONTENT[found.content if found else "text_asset"]
        labels = {"body": "текст", "asset": "ассет", "url": "ссылка", "scene": "сцена карты", "message": "письмо"}

        errors = {}
        for field, filled in used.items():
            if filled and field not in allowed:
                errors[field] = "Для этого формата это поле не используется."
        if not errors:
            chosen = [field for field in allowed if used[field]]
            names = " или ".join(labels[field] for field in sorted(allowed))
            if len(chosen) > 1:
                errors["__all__"] = f"Выберите одно из содержимого: {names}."
            elif not chosen and found and found.content in REQUIRED_CONTENT:
                errors["__all__"] = f"Нужно указать содержимое: {names}."
        if errors:
            raise ValidationError(errors)


class ItemRevision(models.Model):
    """Версия текстового содержимого объекта: снимок, который делается при сохранении, если что-то изменилось."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="revisions")
    name = models.CharField(max_length=200)
    format = models.SlugField(max_length=32, blank=True)
    body = models.TextField(blank=True)
    meta = models.TextField(blank=True)
    saved_at = models.DateTimeField(auto_now_add=True)
    saved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("-saved_at", "-id")
        verbose_name = "Версия объекта"
        verbose_name_plural = "Версии объектов"

    def __str__(self):
        return f"{self.item.slug} @ {self.saved_at:%Y-%m-%d %H:%M}"


class ItemLock(models.Model):
    """Мягкая блокировка объекта на время правки в админке (кто правит сейчас)."""

    item = models.OneToOneField(Item, on_delete=models.CASCADE, related_name="lock")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    acquired_at = models.DateTimeField(auto_now_add=True)
    refreshed_at = models.DateTimeField()

    class Meta:
        verbose_name = "Блокировка объекта"
        verbose_name_plural = "Блокировки объектов"


class ItemMember(models.Model):
    """Член архива: объект-архив содержит другие объекты под своими путями (pak l, pak x)."""

    archive = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="members")
    path = models.CharField("Путь в архиве", max_length=1024, help_text="Например: docs/readme.txt")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="in_archives", verbose_name="Объект")

    class Meta:
        ordering = ("path",)
        constraints = [models.UniqueConstraint(fields=("archive", "path"), name="unique_archive_member")]
        verbose_name = "Член архива"
        verbose_name_plural = "Члены архива"

    def __str__(self):
        return f"{self.archive.slug}: {self.path}"

    def save(self, *args, **kwargs):
        self.path = normalize_inner(self.path)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.path = normalize_inner(self.path)
        if not self.path:
            raise ValidationError({"path": "Укажите путь в архиве."})
        if self.archive_id and self.item_id == self.archive_id:
            raise ValidationError({"item": "Архив не может содержать сам себя."})


class ItemKey(models.Model):
    """Ключ, внедрённый в файл: его блок лежит в байтах объекта и открывается вместе со слоями."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="keys")
    key = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="embedded_in", limit_choices_to={"format": KEY_FORMAT})

    class Meta:
        constraints = [models.UniqueConstraint(fields=("item", "key"), name="unique_item_key")]
        verbose_name = "Внедрённый ключ"
        verbose_name_plural = "Внедрённые ключи"

    def __str__(self):
        return f"{self.item.slug}: {self.key.slug}"

    def clean(self):
        super().clean()
        if self.key_id and self.key.format != KEY_FORMAT:
            raise ValidationError({"key": "Это не ключ: у объекта должен быть формат «key»."})
        if self.key_id and self.key_id == self.item_id:
            raise ValidationError({"key": "Объект не может содержать сам себя."})


class ItemSignature(models.Model):
    """Подпись ключа под объектом, встроенная автором."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="signatures")
    key = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="signed", limit_choices_to={"format": KEY_FORMAT})
    valid = models.BooleanField(default=True, help_text="Снять отметку: подпись не сходится (подделка).")
    date = models.DateField(null=True, blank=True, help_text="Дата подписи в мире игры (необязательно).")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("item", "key"), name="unique_item_signature")]
        verbose_name = "Подпись"
        verbose_name_plural = "Подписи"

    def __str__(self):
        return f"{self.item.slug}: {self.key.slug}"

    def clean(self):
        super().clean()
        if self.key_id and self.key.format != KEY_FORMAT:
            raise ValidationError({"key": "Это не ключ: у объекта должен быть формат «key»."})


class Volume(models.Model):
    """Том: дерево папок и объектов. Не знает, на какой машине лежит; машина монтирует том (machines.MachineMount)."""

    slug = models.SlugField("Слаг", max_length=64, unique=True, help_text="Идентификатор для админки и импорта; в игре не виден.")
    name = models.CharField("Название диска", max_length=128, blank=True, help_text="Как диск называется в игре (проводник, df, vol).")
    uuid = models.UUIDField("UUID", default=uuid.uuid4, unique=True, help_text="Идентификатор в fstab и df; можно задать свой.")
    label = models.CharField("Метка для админки", max_length=128, blank=True, help_text="Чтобы искать том в списках; игрок её не видит.")
    access = models.JSONField(
        "Доступ", default=dict, blank=True, validators=[validate_requirements],
        help_text="Условие по слагам ключей, закрывающее весь том. Пусто: всем.",
    )

    class Meta:
        ordering = ("slug",)
        verbose_name = "Том"
        verbose_name_plural = "Тома"

    def __str__(self):
        return f"{self.slug} ({self.label})" if self.label else self.slug


class Placement(models.Model):
    """Строка дерева тома: папка, объект или надгробие. Так объект кладётся в том."""

    class Kind(models.TextChoices):
        FOLDER = "folder", "Папка"
        ITEM = "item", "Объект"
        WHITEOUT = "whiteout", "Надгробие"

    class Mode(models.TextChoices):
        INHERIT = "inherit", "Как у объекта"
        REPLACE = "replace", "Заменить"
        NONE = "none", "Нет"

    volume = models.ForeignKey(Volume, on_delete=models.CASCADE, related_name="placements")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.ITEM)
    name = models.CharField(
        "Имя", max_length=255, blank=True, validators=[validate_name],
        help_text="Имя в этом месте. Пусто: берётся имя объекта с расширением формата. Точка в начале скрывает файл.",
    )
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.PROTECT, related_name="placements", verbose_name="Объект")
    hidden = models.BooleanField("Скрыт", default=False, help_text="Скрытое не показывает ls без -a.")

    access_mode = models.CharField("Доступ", max_length=8, choices=Mode.choices, default=Mode.INHERIT)
    access = models.JSONField("Условие доступа", default=dict, blank=True, validators=[validate_requirements])
    state_mode = models.CharField("Слои", max_length=8, choices=Mode.choices, default=Mode.INHERIT)
    state = models.TextField("Слои защиты", blank=True)

    system = models.BooleanField("Системный", default=False, help_text="Игрок не может удалить.")

    class Meta:
        ordering = ("volume", "parent_id", "name")
        verbose_name = "Размещение"
        verbose_name_plural = "Размещения"
        constraints = [
            models.UniqueConstraint(fields=("volume", "parent", "name"), condition=Q(parent__isnull=False), name="unique_placement_name"),
            models.UniqueConstraint(fields=("volume", "name"), condition=Q(parent__isnull=True), name="unique_placement_root_name"),
            models.CheckConstraint(
                condition=(Q(kind="item", item__isnull=False) | (~Q(kind="item") & Q(item__isnull=True))),
                name="placement_item_only_for_items",
            ),
        ]

    def __str__(self):
        return f"{self.volume.slug}:/{self.path()}"

    def path(self):
        """Путь внутри тома (без ведущего слэша)."""
        names, node, seen = [], self, set()
        while node is not None and node.pk not in seen:
            names.append(node.name)
            seen.add(node.pk)
            node = node.parent
        return "/".join(reversed(names))

    def depth(self):
        depth, node, seen = 0, self.parent, set()
        while node is not None and node.pk not in seen:
            depth += 1
            seen.add(node.pk)
            node = node.parent
        return depth

    def save(self, *args, **kwargs):
        if not self.name and self.item_id:
            self.name = self.item.default_filename
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if not self.name and self.item_id:
            self.name = self.item.default_filename                  # до проверки уникальности: дубль должен быть ошибкой формы
        errors = {}
        if self.kind == self.Kind.ITEM and self.item_id is None:
            errors["item"] = "Укажите объект."
        if self.kind != self.Kind.ITEM and self.item_id is not None:
            errors["item"] = "Объект указывается только у размещения вида «Объект»."
        if not self.name and self.item_id is None:
            errors["name"] = "Укажите имя."
        if self.parent_id is not None:
            if self.parent.kind != self.Kind.FOLDER:
                errors["parent"] = "Родитель должен быть папкой."
            elif self.parent.volume_id != self.volume_id:
                errors["parent"] = "Родитель из другого тома."
            elif self.pk and self._loops():
                errors["parent"] = "Родитель создаёт цикл."
            elif self.depth() >= MAX_DEPTH:
                errors["parent"] = f"Максимальная вложенность: {MAX_DEPTH}."
        for field, mode, value in (("access", self.access_mode, self.access), ("state", self.state_mode, self.state)):
            if mode == self.Mode.REPLACE and not value:
                errors[field] = "Режим «Заменить» требует заполненного поля (чтобы убрать, выберите «Нет»)."
        if errors:
            raise ValidationError(errors)
        if self.name:
            validate_name(self.name)

    def _loops(self):
        node, seen = self.parent, {self.pk}
        while node is not None:
            if node.pk in seen:
                return True
            seen.add(node.pk)
            node = node.parent
        return False


class VolumeInstance(models.Model):
    """Экземпляр тома: пара (том, хост). Место, где живёт состояние игрока.

    local-монтирование тома на машине M даёт экземпляр (том, M); remote указывает на экземпляр хоста. Хост пуст у тома, который
    отдаёт не машина (внешний источник)."""

    volume = models.ForeignKey(Volume, on_delete=models.CASCADE, related_name="instances")
    host = models.ForeignKey("machines.Machine", null=True, blank=True, on_delete=models.CASCADE, related_name="hosted_volumes")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("volume", "host"), condition=Q(host__isnull=False), name="unique_instance_host"),
            models.UniqueConstraint(fields=("volume",), condition=Q(host__isnull=True), name="unique_instance_external"),
        ]
        verbose_name = "Экземпляр тома"
        verbose_name_plural = "Экземпляры томов"

    def __str__(self):
        return f"{self.volume.slug} @ {self.host.label if self.host_id else 'external'}"


class PlayerFile(models.Model):
    """Слой игрока: одно отличие игрока от общей базы по одному пути внутри тома.

    У записи либо ссылка на объект (item), либо собственное содержимое: content (текст, например подпись) или data (байты,
    например вырезка). Для записи с объектом content это своя версия его тела (правка edt).
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="player_files")
    instance = models.ForeignKey(VolumeInstance, on_delete=models.CASCADE, related_name="player_files")
    path = models.CharField("Путь в томе", max_length=2048)
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.CASCADE, related_name="player_files")
    content = models.TextField(null=True, blank=True)
    data = models.BinaryField(null=True, blank=True)
    state = models.TextField(blank=True, default="")
    deleted_at = models.DateTimeField(null=True, blank=True, help_text="Файл удалён игроком (надгробие).")

    # корзина (del): файл лежит в корзине, пока не истечёт purge_at
    origin_path = models.CharField(max_length=2048, blank=True, default="")
    trashed_at = models.DateTimeField(null=True, blank=True)
    purge_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "instance", "path"), name="unique_player_file_path"),
            models.CheckConstraint(
                condition=~(Q(item__isnull=False) & Q(data__isnull=False)), name="player_file_item_or_data",
            ),
        ]
        indexes = [models.Index(fields=("user", "instance"), name="playerfile_user_instance_idx")]
        verbose_name = "Файл игрока"
        verbose_name_plural = "Файлы игроков"

    def __str__(self):
        return f"{self.user_id}: {self.instance}:/{self.path}"

    def save(self, *args, **kwargs):
        self.path = normalize_inner(self.path)
        super().save(*args, **kwargs)
