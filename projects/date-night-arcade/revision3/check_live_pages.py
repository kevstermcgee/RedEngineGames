import pathlib,json,hashlib,time
from playwright.sync_api import sync_playwright
R=pathlib.Path(__file__).parent;meta=json.loads((R.parent/'publish-repo/site/browser-downloads.json').read_text());base='https://kevstermcgee.github.io/RedEngineGames/';rows=[]
with sync_playwright()as pw:
 browser=pw.chromium.launch();ctx=browser.new_context(accept_downloads=True);page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'?revision=survival-2');page.wait_for_selector('#games');assert page.locator('.game[data-id^="web:"]').count()>0
 for id in meta:
  card=page.locator(f'.game[data-id="web:{id}"]');href=card.locator('.card-links a').first.get_attribute('href');assert href==f'browser/{id}/'
 page.select_option('#pres','2d');assert page.locator('.game:not(.hidden)[data-id^="win:"]').count()==0
 page.select_option('#pres','3d');assert page.locator('.game:not(.hidden)[data-pres="2d"]').count()==0
 for id in meta:
  page.goto(base+'browser/'+id+'/?revision=survival-2');assert page.locator('h2').first.inner_text();assert 'Four hearts' in page.inner_text('body');assert 'F toggles fullscreen' in page.inner_text('body')
  assert page.locator('a.dl').filter(has_text='Install for Windows').get_attribute('href')==meta[id]['url']
  page.locator('a.dl').filter(has_text='Play now').click();page.wait_for_function('() => window.__red2d && __red2d.status().state === "ready"')
  page.locator('#install').click();assert page.locator('dialog').is_visible()
  with page.expect_download(timeout=30000)as event:page.locator('#windows-download').click()
  download=event.value;assert download.suggested_filename=='setup-'+id+'.exe';path=pathlib.Path('/tmp')/download.suggested_filename;download.save_as(path);assert hashlib.sha256(path.read_bytes()).hexdigest()==meta[id]['sha256'];path.unlink()
  page.locator('#install-close').click();page.mouse.click(40,70);page.wait_for_function('() => __red2d.status().music === "playing"',timeout=30000)
  page.keyboard.press('f');page.wait_for_function('() => !!document.fullscreenElement');page.keyboard.press('f');page.wait_for_function('() => !document.fullscreenElement')
  rows.append({'game':id,'human_game_page':True,'installer_download_sha256':meta[id]['sha256'],'actual_game_install_button':True,'live_music_playback':True,'live_fullscreen_F':True});print(id,'live page and installer download PASS',flush=True)
 assert not errors,errors;browser.close()
(R/'evidence/live-pages.json').write_text(json.dumps(rows,indent=2)+'\n')
