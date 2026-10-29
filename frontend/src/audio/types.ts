export type AudioPreferences = {
  music_enabled: boolean; sounds_enabled: boolean; music_volume: number; sounds_volume: number
}
export const defaultAudio: AudioPreferences = {
  music_enabled: false, sounds_enabled: false, music_volume: 25, sounds_volume: 35,
}
