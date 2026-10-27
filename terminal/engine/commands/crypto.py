from dataclasses import replace

from filesystem import archives, keystore
from filesystem.rawview import keys, signatures
from secure.models import Key
from terminal.engine.rawinfo import raw_of
from terminal.scenes import key_scene, sign_scene, verify_scene
from terminal.engine.commands.layered import LayerCommand
from terminal.engine.filesystem import VirtualFilesystem
from terminal.engine.result import CommandResult


class WardCommand(LayerCommand):
    """ward <файл> <пароль>: снять шифрование (слой encrypted). Архивы он не открывает: у них свой пароль (pak pass).

    ward verify <файл>                  проверить подписи, лежащие в самом файле
    ward verify <подпись> <файл>        проверить отдельный файл подписи (.sig)
    ward sign -k <ключ> <файл>          подписать файл ключом из /home/.secrets, подпись ляжет рядом (<файл>.sig)"""

    name = "ward"
    layer = "encrypted"
    done = "decrypted"
    absent = "not encrypted"

    USAGE = "usage: ward file password\n       ward -k keyname file\n       ward verify [signature] file\n       ward sign -k keyname file\n       ward keys"

    def execute(self, context, args):
        if args and args[0] == "verify":
            return self.verify(context, args[1:])
        if args and args[0] == "sign":
            return self.sign(context, args[1:])
        if args and args[0] == "keys":
            return self.list_keys(context)
        if args and args[0] == "-k":
            return self.with_key(context, args[1:])
        if args:
            entry = VirtualFilesystem(context).get_file(context.resolve_path(args[0]))
            if entry is not None and archives.is_archive(entry.machine_file):
                return CommandResult(f"{self.name}: {args[0]}: no valid data found", 1)        # как gpg на чужом файле
        if not args:
            return CommandResult("ward: missing file operand", 2)
        if len(args) == 1:
            return CommandResult("ward: missing password", 2)
        if len(args) > 2:
            return CommandResult("ward: too many arguments", 2)
        result = self.unlock(context, args[0], [], self.layer, given={"password": args[1]})
        if result.exit_code == 0 and "decrypted" in result.output:
            return replace(result, output="ward: AES256.CFB encrypted data\nward: encrypted with 1 passphrase\n" + result.output)
        return result

    def fail_for(self, context, entry, target, wrong, values):
        reason = "No secret key" if "key" in wrong.split(", ") else "Bad session key"
        return f"{self.name}: decryption failed: {reason}"

    def held_key(self, context, name):
        """slug ключа с таким именем в /home/.secrets или None."""
        return name if name in keystore.slugs_of(context.session) else None

    def with_key(self, context, args):
        if len(args) != 2:
            return CommandResult(self.USAGE, 2)
        name, target = args
        slug = self.held_key(context, name)
        if slug is None:
            return CommandResult(f"ward: no secret key '{name}' in {keystore.SECRETS}", 1)
        entry = VirtualFilesystem(context).get_file(context.resolve_path(target))
        if entry is not None and archives.is_archive(entry.machine_file):
            return CommandResult(f"{self.name}: {target}: no valid data found", 1)
        result = self.unlock(
            context, target, [], self.layer, given={"key": slug},
            scene=lambda item, ok, rest: key_scene(item.path, ok),
        )
        if result.exit_code == 0 and "decrypted" in result.output:
            head = f"ward: encrypted with RSA key, ID {keys.key_id(slug).hex().upper()}\n      \"{slug}\"\n"
            return replace(result, output=head + result.output)
        return result

    def list_keys(self, context):
        rows = []
        for filename, slug in keystore.held(context.session):
            note = Key.objects.filter(slug=slug).values_list("description", flat=True).first() or ""
            rows.append((keys.key_id(slug).hex().upper(), slug, filename, note.strip().splitlines()[0] if note.strip() else ""))
        if not rows:
            return CommandResult(f"ward: no keys in {keystore.SECRETS}", 1)
        width = max(len(slug) for _, slug, _, _ in rows)
        return CommandResult(
            "\n".join(f"{ident}  {slug:<{width}}  {filename}" + (f"  {note}" if note else "") for ident, slug, filename, note in rows), 0
        )

    def _open(self, context, target):
        """(запись, байты) файла или (None, ответ с ошибкой)."""
        fs = VirtualFilesystem(context)
        path = context.resolve_path(target)
        if not fs.exists(path):
            return None, CommandResult(f"ward: cannot open '{target}': No such file or directory", 2)
        if fs.is_directory(path):
            return None, CommandResult(f"ward: {target}: Is a directory", 1)
        entry = fs.get_file(path)
        return entry, raw_of(context, entry).data

    def verify(self, context, args):
        if len(args) not in (1, 2):
            return CommandResult("usage: ward verify file\n       ward verify signature file", 2)
        if len(args) == 1:
            entry, data = self._open(context, args[0])
            if entry is None:
                return data
            found = signatures.find(data)
            content = data[:found[0]["start"]] if found else data
        else:
            sig, sig_data = self._open(context, args[0])
            if sig is None:
                return sig_data
            entry, content = self._open(context, args[1])
            if entry is None:
                return content
            found = signatures.find(sig_data)

        if not found:
            return CommandResult(f"ward: {args[-1]}: no signature found", 1, scene=verify_scene(entry.path, 0, False))

        lines, good = [], 0
        for item in found:
            if not Key.objects.filter(slug=item["slug"]).exists():
                lines.append(f"ward: Can't check signature: No public key ({item['slug']})")
                continue
            if item["date"]:
                lines.append(f"ward: Signature made {item['date']} using key {item['slug']}")
            if signatures.check(item, content):
                good += 1
                lines.append(f"ward: Good signature from {item['slug']}")
            else:
                lines.append(f"ward: BAD signature from {item['slug']}")
        ok = good == len(found)
        return CommandResult("\n".join(lines), 0 if ok else 1, scene=verify_scene(entry.path, len(found), ok))

    def sign(self, context, args):
        if len(args) != 3 or args[0] != "-k":
            return CommandResult("usage: ward sign -k keyname file", 2)
        name, target = args[1], args[2]
        fs = VirtualFilesystem(context)
        if self.held_key(context, name) is None:
            return CommandResult(f"ward: no secret key '{name}' in {keystore.SECRETS}", 1)
        entry, data = self._open(context, target)
        if entry is None:
            return data
        output = entry.path + ".sig"
        if fs.exists(output):
            return CommandResult(f"ward: '{output}' exists, delete it first", 1)
        keystore.put_signature(context.session, name, signatures.digest(data), output)
        return CommandResult(f"ward: signed {target} with key {name}\n  {output}", 0, scene=sign_scene(entry.path, name))
