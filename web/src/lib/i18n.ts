import { useCallback } from 'react'
import messages from './i18n.messages.json'
import { useProjectStore } from '@/store/projectStore'
import type { UiLocale } from '@/store/projectStore'

const en = messages.en
export type TranslationKey = keyof typeof en

const TABLE = {
  en,
  es: messages.es,
  'zh-CN': messages['zh-CN'],
  ja: messages.ja,
} satisfies Record<UiLocale, Partial<Record<TranslationKey, string>>>

export function tKey(key: TranslationKey): string {
  const locale = useProjectStore.getState().appSettings.locale
  return (TABLE[locale] as Partial<Record<TranslationKey, string>>)[key] ?? en[key] ?? key
}

export function useT() {
  const locale = useProjectStore((s) => s.appSettings.locale)
  return useCallback(
    (key: TranslationKey): string =>
      (TABLE[locale] as Partial<Record<TranslationKey, string>>)[key] ?? en[key] ?? key,
    [locale]
  )
}
