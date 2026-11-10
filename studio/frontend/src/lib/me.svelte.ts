// Кто вошёл в Студию и что ему можно (team.rights): уровень по разделам, опасные действия, управление командой.
import { api, type Schemas } from "./api";

export const me = $state<{ loaded: boolean; data: Schemas["Me"] | null }>({ loaded: false, data: null });

export async function loadMe(): Promise<void> {
  me.data = (await api.GET("/studio/api/me")).data ?? null;
  me.loaded = true;
}

/** Уровень раздела: none, read или edit. Пока не загрузилось, считается edit, чтобы экран не мигал запретом. */
export function level(section: string): string {
  if (!me.data) return "edit";
  return me.data.rights.sections[section] ?? "edit";
}

export const canEdit = (section: string) => level(section) === "edit";
export const canAct = (action: string) => !me.data || me.data.rights.actions.includes(action);
export const isSuper = () => !!me.data?.superuser;
