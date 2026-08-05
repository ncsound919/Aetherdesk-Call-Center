import html2canvas from 'html2canvas'

export async function exportFlyerToPng(element, filename = 'flyer.png') {
  if (!element) throw new Error('Flyer element not found')
  const canvas = await html2canvas(element, {
    backgroundColor: null,
    scale: 2,
    useCORS: true,
    logging: false,
  })
  const dataUrl = canvas.toDataURL('image/png')
  const link = document.createElement('a')
  link.download = filename
  link.href = dataUrl
  link.click()
  return dataUrl
}
