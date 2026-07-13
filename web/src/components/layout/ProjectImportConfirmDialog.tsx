import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useT } from '@/lib/i18n'
import type { TranslationKey } from '@/lib/i18n'

export function ProjectImportConfirmDialog({
  open,
  onOpenChange,
  onConfirm,
  titleKey = 'file_import_confirm_title',
  bodyKey = 'file_import_confirm_body',
  confirmKey = 'file_import_json',
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  titleKey?: TranslationKey
  bodyKey?: TranslationKey
  confirmKey?: TranslationKey
}) {
  const t = useT()

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent size="sm">
        <AlertDialogHeader>
          <AlertDialogTitle>{t(titleKey)}</AlertDialogTitle>
          <AlertDialogDescription>{t(bodyKey)}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('dialog_cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={onConfirm}>
            {t(confirmKey)}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
