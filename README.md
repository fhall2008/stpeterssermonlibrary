# St. Peter's Hornsby — Sermon Library

A static GitHub Pages site that fetches and displays sermons from your Anchor/Spotify RSS feed with filtering by speaker, book, topic, series, and service.

## Setup & Deployment

### 1. Create a GitHub Repository
1. Go to [github.com](https://github.com) → **New repository**
2. Name it `sermons` (or anything you like)
3. Set it to **Public**
4. Click **Create repository**

### 2. Upload the file
Upload `index.html` to the repository root.

### 3. Enable GitHub Pages
1. Go to **Settings → Pages**
2. Under **Source**, select **Deploy from a branch**
3. Choose `main` branch, `/ (root)` folder
4. Click **Save**

Your site will be live at: `https://YOUR-USERNAME.github.io/REPO-NAME/`

---

## Adding Farsi Sermons

When you have your Farsi RSS feed ready:

1. Open `index.html`
2. Find the line:
   ```js
   var RSS_EN = 'https://anchor.fm/s/c1de3e94/podcast/rss';
   ```
3. Add below it:
   ```js
   var RSS_FA = 'YOUR_FARSI_RSS_FEED_URL';
   ```
4. Find the `tab-fa` button and remove the `inactive-lang` class, change its `onclick` to `setLang('fa')`
5. Update `loadFeed()` to load the Farsi feed when `lang === 'fa'`

Or simply message us and we'll update the code for you!

---

## How filters work

The library automatically extracts metadata from each sermon's RSS description:

| Filter | How it's detected |
|---|---|
| **Speaker** | iTunes `<author>` tag, or "Speaker: Name" pattern in description |
| **Book** | Scans for any of 66 Bible book names |
| **Topic** | "Topic: X" or "Theme: X" patterns in description |
| **Series** | "Series: X" or "Part N of X" patterns in description |
| **Service** | Time/service keywords: "Sunday Morning", "9am", "Easter", etc. |

> **Tip:** The more structured your episode descriptions on Anchor/Spotify, the better the auto-detection. Adding lines like `Series: The Lord's Prayer` or `Speaker: Rev. John Smith` will improve filtering accuracy.
