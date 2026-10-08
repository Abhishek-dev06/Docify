import { test, expect } from '@playwright/test';

test('photo replacement case is available in the actual dashboard', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Synthetic scenario').selectOption('photo_replaced');
  await page.getByRole('button', {name:'Load synthetic sample'}).click();
  await expect(page.getByText('synthetic_photo_replaced_document.png')).toBeVisible();
  await expect(page.getByText('synthetic_photo_replaced_live.png')).toBeVisible();
  await expect(page.getByRole('button', {name:'Analyze & record'})).toBeEnabled();
  await expect(page.getByLabel('Portrait region')).toHaveValue('[0.75,0.21,0.19375,0.46]');
  await page.screenshot({path:'../reports/phase6/demo_photo_replaced.png',fullPage:true});
});
