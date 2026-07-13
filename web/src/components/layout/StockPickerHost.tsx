import { StockPhotosModal } from '@/components/layout/StockPhotosModal'
import { StockVideosModal } from '@/components/layout/StockVideosModal'

export function StockPickerHost() {
  return (
    <>
      <StockPhotosModal />
      <StockVideosModal />
    </>
  )
}
