interface BundledPersonaAvatar {
  id: string;
  label: string;
  url: string;
}

const FEMALE_AVATARS: BundledPersonaAvatar[] = Array.from({ length: 8 }, (_, index) => ({
  id: `female_${index + 1}`,
  label: `Female Avatar ${index + 1}`,
  url: `/personas/avatars/female_avatar_${index + 1}.png`,
}));

const MALE_AVATARS: BundledPersonaAvatar[] = Array.from({ length: 4 }, (_, index) => ({
  id: `male_${index + 1}`,
  label: `Male Avatar ${index + 1}`,
  url: `/personas/avatars/male_avatar_${index + 1}.png`,
}));

export const bundledPersonaAvatars: BundledPersonaAvatar[] = [
  ...FEMALE_AVATARS,
  ...MALE_AVATARS,
];

export function fallbackPersonaAvatarUrl(index = 0): string {
  if (bundledPersonaAvatars.length === 0) {
    return "";
  }
  const safeIndex = Math.abs(index) % bundledPersonaAvatars.length;
  return bundledPersonaAvatars[safeIndex]?.url ?? bundledPersonaAvatars[0].url;
}

export function normalizePersonaHandle(displayName: string, explicitName = ""): string {
  const base = (explicitName.trim() || displayName.trim()).toLowerCase();
  const slug = base
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_{2,}/g, "_");
  return slug || "persona";
}
