import { expect, test } from '@playwright/test'

function grayscaleBmp(width: number, height: number, value: number): Buffer {
  const rowSize = Math.ceil(width * 3 / 4) * 4; const pixelBytes = rowSize * height; const output = Buffer.alloc(54 + pixelBytes)
  output.write('BM'); output.writeUInt32LE(output.length, 2); output.writeUInt32LE(54, 10); output.writeUInt32LE(40, 14); output.writeInt32LE(width, 18); output.writeInt32LE(height, 22); output.writeUInt16LE(1, 26); output.writeUInt16LE(24, 28); output.writeUInt32LE(pixelBytes, 34)
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) { const offset = 54 + y * rowSize + x * 3; const sample = (value + x + y) % 256; output[offset] = sample; output[offset + 1] = sample; output[offset + 2] = sample }
  return output
}

async function makeTiff(): Promise<Buffer> {
  const form = new FormData()
  form.append('files', new Blob([grayscaleBmp(32, 24, 20)], { type: 'image/bmp' }), '450.bmp')
  form.append('files', new Blob([grayscaleBmp(32, 24, 140)], { type: 'image/bmp' }), '850.bmp')
  form.append('channel_names', '["450nm","850nm"]'); form.append('response_mode', 'direct'); form.append('output_name', 'sample.tif')
  const response = await fetch('http://127.0.0.1:5000/api/v1/convert/bmp-to-tiff', { method: 'POST', body: form })
  expect(response.ok).toBeTruthy(); return Buffer.from(await response.arrayBuffer())
}

test('Workflow A: BMP reorder, conversion, result, and TIFF download', async ({ page }) => {
  await page.goto('/convert')
  await page.getByLabel('Drop grayscale BMP bands here').setInputFiles([
    { name: '450.bmp', mimeType: 'image/bmp', buffer: grayscaleBmp(32, 24, 20) },
    { name: '850.bmp', mimeType: 'image/bmp', buffer: grayscaleBmp(32, 24, 140) },
  ])
  await page.getByLabel('Move Channel 2 up').click()
  await expect(page.locator('.band-row').first()).toContainText('850.bmp')
  await page.getByLabel('Channel 1 name').fill('850nm'); await page.getByLabel('Channel 2 name').fill('450nm')
  await page.getByRole('button', { name: 'Convert to TIF' }).click()
  await expect(page).toHaveURL(/\/convert\/result\//); await expect(page.getByRole('heading', { name: 'Your TIFF is ready' })).toBeVisible()
  const download = page.waitForEvent('download'); await page.getByRole('link', { name: 'Download TIF' }).click(); expect((await download).suggestedFilename()).toMatch(/\.tif$/)
})

test('Workflow B: TIFF viewer modes and annotator resource transfer', async ({ page }) => {
  const source = await makeTiff(); await page.goto('/viewer'); await page.getByLabel('Drop a multispectral TIFF here').setInputFiles({ name: 'sample.tif', mimeType: 'image/tiff', buffer: source })
  await expect(page.getByRole('heading', { name: 'sample.tif' })).toBeVisible(); await page.getByRole('button', { name: 'Next channel' }).click(); await expect(page.getByText('Channel 2 / 2')).toBeVisible()
  await page.getByRole('button', { name: /Grid/ }).click(); await page.getByRole('button', { name: /Channel 1.*450nm/ }).click(); await expect(page.getByText('Channel 1 / 2')).toBeVisible()
  const resourceId = await page.evaluate(() => sessionStorage.getItem('mulan:active-image')); await page.getByRole('button', { name: 'Open in Annotator' }).click(); await expect(page).toHaveURL(new RegExp(`annotator\\?image_id=${resourceId}`)); await expect(page.getByText('Semantic layers')).toBeVisible()
})

test('Workflow C: aligned annotation, channel change, save, and export', async ({ page }) => {
  const source = await makeTiff(); await page.goto('/annotator'); await page.getByLabel('Drop a multispectral TIFF here').setInputFiles({ name: 'sample.tif', mimeType: 'image/tiff', buffer: source }); await expect(page.getByText('Semantic layers')).toBeVisible()
  await page.getByRole('button', { name: 'Add class' }).click(); const dialog = page.getByRole('dialog', { name: 'Add class' }); await dialog.getByLabel('Name').fill('Vegetation'); await dialog.getByRole('button', { name: 'Add class' }).click(); await expect(page.getByText('Vegetation')).toBeVisible()
  await page.getByRole('button', { name: 'Rectangle Add' }).click(); const canvas = page.locator('.annotation-canvas canvas').first(); const box = await canvas.boundingBox(); expect(box).toBeTruthy(); if (box) await page.mouse.move(box.x + box.width * .35, box.y + box.height * .35).then(() => page.mouse.down()).then(() => page.mouse.move(box.x + box.width * .6, box.y + box.height * .6)).then(() => page.mouse.up())
  await expect(page.getByText(/Unsaved changes/)).toBeVisible(); await page.getByRole('button', { name: 'Next channel' }).click(); await expect(page.getByText('Channel 2 / 2')).toBeVisible(); await expect(page.getByText(/Unsaved changes/)).toBeVisible()
  await page.getByRole('button', { name: 'Save changes' }).click(); await expect(page.getByRole('dialog', { name: 'Annotation saved' })).toBeVisible(); const download = page.waitForEvent('download'); await page.getByRole('link', { name: 'Download Mask' }).click(); expect((await download).suggestedFilename()).toBe('annotation-mask.zip')
})
