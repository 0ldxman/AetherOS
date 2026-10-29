"""Запись в слой игрока: проверка прав, новые файлы, правка, удаление, копирование."""
from django.utils import timezone

from filesystem import instances, rights
from filesystem.machine_view.entries import DATA_LIMIT, Occupied, ReadOnly
from filesystem.models import PlayerFile


class WriteMixin:
    def _may(self, path, action):
        rights.check(self, self.principal, path, action)

    def _may_write(self, path):
        """Записать path: файл есть, нужно право на него, иначе на папку, где он появится."""
        if self.principal is None:
            return
        found = self.get(path)
        if found is not None and not found.is_dir:
            self._may(path, "w")
        else:
            rights.check_parent(self, self.principal, self._clean(path))

    def _fresh(self, path, source=None):
        """Права нового файла игрока: владелец он, режим 644 (копия берёт режим источника, перенос ещё и владельца)."""
        if self.principal is None or self.get(path) is not None:
            return {}
        if source is None:
            return {"owner": self.principal.login, "group": "", "mode": "644"}
        return source

    def _target(self, path):
        """Слой, куда ляжет новое по этому пути: верхний из покрывающих его монтирований."""
        path = self._clean(path)
        if path in {layer.point for layer in self.layers}:
            raise Occupied(path)
        for attempt in range(2):
            for layer in reversed(self.layers):
                inner = layer.inner_path(path)
                if inner:
                    return layer, inner
            if attempt == 0 and not any(layer.point == "/" for layer in self.layers):
                from filesystem.manager.provision import ensure_root

                ensure_root(self.machine)                    # у машины ещё нет корня: он появляется с первой записью
                self.invalidate()
        raise ReadOnly(path)

    def _row(self, layer, inner):
        instance = layer.instance or instances.get_or_create(layer.mount.volume_id, layer.host_id)
        row, _ = PlayerFile.objects.get_or_create(user=self.user, instance=instance, path=inner)
        return row

    def _save(self, row, **fields):
        for name, value in fields.items():
            setattr(row, name, value)
        row.save()
        self.invalidate()
        return row

    def _clear(self, **fields):
        return {"deleted_at": None, "origin_path": "", "trashed_at": None, "purge_at": None, **fields}

    def put_item(self, path, item, state="", content=None, rights_fields=None):
        """Положить ссылку на объект (cp, mv, распаковка, вложение письма, ключ в папку секретов)."""
        done, result = self._delegate(path, "put_item", item, state, content, rights_fields)
        if done:
            return result
        self._may_write(path)
        fresh = self._fresh(path, rights_fields)
        layer, inner = self._target(path)
        return self._save(self._row(layer, inner), **self._clear(item=item, content=content, data=None, state=state), **fresh)

    def put_text(self, path, text, state="", rights_fields=None):
        """Файл игрока без объекта с текстом (подпись)."""
        done, result = self._delegate(path, "put_text", text, state, rights_fields)
        if done:
            return result
        self._may_write(path)
        fresh = self._fresh(path, rights_fields)
        layer, inner = self._target(path)
        return self._save(self._row(layer, inner), **self._clear(item=None, content=text, data=None, state=state), **fresh)

    def put_data(self, path, data, state="", rights_fields=None):
        """Файл игрока без объекта с байтами (вырезка)."""
        done, result = self._delegate(path, "put_data", data, state, rights_fields)
        if done:
            return result
        if len(data) > DATA_LIMIT:
            raise ValueError("too large")
        self._may_write(path)
        fresh = self._fresh(path, rights_fields)
        layer, inner = self._target(path)
        return self._save(self._row(layer, inner), **self._clear(item=None, content=None, data=bytes(data), state=state), **fresh)

    def edit_text(self, path, text):
        """Своя версия текста существующего файла."""
        done, result = self._delegate(path, "edit_text", text)
        if done:
            return result
        found = self.get(path)
        if found is None or found.is_dir:
            raise FileNotFoundError(path)
        self._may(path, "w")
        row = self._row(found.layer, found.inner)
        fields = {"content": text, "data": None, "deleted_at": None}
        if found.item is not None:
            fields["item"] = found.item                                   # правка тела объекта: ссылка остаётся
        return self._save(row, **fields)

    def set_rights(self, path, **fields):
        """Права файла в слое игрока: owner, group, mode (только переданные поля)."""
        done, result = self._delegate(path, "set_rights", **fields)
        if done:
            return result
        found = self.get(path)
        if found is None or found.layer is None:
            raise FileNotFoundError(path)                               # папка без слоя придумана видом: права ей не задать
        row = found.player or self._row(found.layer, found.inner)
        return self._save(row, **fields)

    def set_progress(self, path, state):
        """Прогресс игрока по слоям файла."""
        done, result = self._delegate(path, "set_progress", state)
        if done:
            return result
        found = self.get(path)
        if found is None or (found.is_dir and found.placement is None):
            raise FileNotFoundError(path)
        row = found.player or self._row(found.layer, found.inner)
        return self._save(row, state=state)

    def remove(self, path):
        """Удалить файл или папку со всем внутри. Возвращает число удалённых файлов."""
        done, result = self._delegate(path, "remove")
        if done:
            return result
        count = 0
        if self.principal is not None:
            rights.check_parent(self, self.principal, self._clean(path))
        for found in reversed(self.under(path)):
            if found.layer is None or found.via is not None:
                continue
            count += not found.is_dir
            for _ in range(3):                                              # файл нижнего слоя мог просвечивать сквозь удалённый
                self._delete_one(found)
                self.invalidate()
                found = self.get(found.path)
                if found is None or found.is_dir or found.layer is None:
                    break
        self.invalidate()
        return count

    def _delete_one(self, found):
        row = found.player
        if row is not None and not found.has_base:
            row.delete()                                                    # файл игрока: следа не остаётся
        else:
            self._save(self._row(found.layer, found.inner), deleted_at=timezone.now(), item=None, content=None, data=None, state="")

    def copy(self, source, target, keep_owner=False):
        """Скопировать файл или папку: те же объекты и прогресс, свои копии записей. Возвращает число файлов.
        Копия принадлежит копирующему и берёт режим источника; при переносе (keep_owner) остаются и владелец с группой."""
        count = 0
        base = self._clean(source)
        for found in self.under(source):
            if found.is_dir:
                continue
            if self.principal is not None:
                self._may(found.path, "r")
            destination = self._clean(target + found.path[len(base):])
            self._put_like(destination, found, keep_owner)
            count += 1
        return count

    def move(self, source, target):
        count = self.copy(source, target, keep_owner=True)
        if self._clean(target) != self._clean(source):
            self.remove(source)
        return count

    def _put_like(self, path, found, keep_owner=False):
        carried = None
        if self.principal is not None and (keep_owner or self.remote_route(path) is None):
            carried = (
                {"owner": found.owner, "group": found.group, "mode": found.mode} if keep_owner
                else {"owner": self.principal.login, "group": "", "mode": found.mode or "644"}
            )
        if found.item is not None:
            self.put_item(path, found.item, found.progress, found.text_override, carried)
        elif found.own_data is not None:
            self.put_data(path, found.own_data, found.progress, carried)
        else:
            self.put_text(path, found.own_text or "", found.progress, carried)
