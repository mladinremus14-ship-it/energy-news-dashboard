const express = require("express");
const cors = require("cors");
const Parser = require("rss-parser");

const app = express();
const parser = new Parser({
  timeout: 12000,
  headers: {
    "User-Agent": "Mozilla/5.0 EnergyNewsDashboard/1.0",
  },
});

const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

const SOURCES = [
  {
    name: "OilPrice",
    url: "https://oilprice.com/rss/main",
  },
  {
    name: "CNBC Energy",
    url: "https://www.cnbc.com/id/19836768/device/rss/rss.html",
  },
  {
    name: "EIA Today in Energy",
    url: "https://www.eia.gov/rss/todayinenergy.xml",
  },
  {
    name: "EIA Natural Gas",
    url: "https://www.eia.gov/rss/naturalgas.xml",
  },
  {
    name: "Google News Energy",
    url: "https://news.google.com/rss/search?q=WTI%20OR%20Brent%20OR%20natural%20gas%20OR%20LNG%20OR%20OPEC%20OR%20Hormuz%20OR%20Iran%20energy&hl=en-US&gl=US&ceid=US:en",
  },
];

const WATCH_TERMS = [
  "wti","brent","crude","oil","natural gas","lng",
  "opec","eia","iran","hormuz","tanker","germany","trump"
];

function cleanText(value = "") {
  return String(value)
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function includesAny(text, terms) {
  const low = text.toLowerCase();
  return terms.some(term => low.includes(term));
}

function classify(text = "") {
  const low = text.toLowerCase();

  if (
    low.includes("hormuz") ||
    low.includes("attack") ||
    low.includes("missile") ||
    low.includes("war")
  ) {
    return {
      level: "RED",
      impact: 92,
      sentiment: "BULLISH",
    };
  }

  if (
    low.includes("eia") ||
    low.includes("inventory") ||
    low.includes("opec")
  ) {
    return {
      level: "ORANGE",
      impact: 68,
      sentiment: "NEUTRU",
    };
  }

  return {
    level: "YELLOW",
    impact: 45,
    sentiment: "NEUTRU",
  };
}

async function fetchSource(source) {
  const feed = await parser.parseURL(source.url);

  return (feed.items || []).map((item, index) => {
    const title = cleanText(item.title || "");
    const summary = cleanText(item.contentSnippet || "");

    const cls = classify(`${title} ${summary}`);

    return {
      id: `${source.name}-${index}`,
      source: source.name,
      title,
      summary,
      url: item.link || source.url,
      createdAt: item.isoDate || new Date().toISOString(),
      level: cls.level,
      impact: cls.impact,
      sentiment: cls.sentiment,
    };
  });
}

let cache = {
  updatedAt: null,
  items: [],
};

async function refreshNews() {
  const results = [];

  await Promise.allSettled(
    SOURCES.map(async (source) => {
      try {
        const items = await fetchSource(source);
        results.push(...items);
      } catch (err) {
        console.log(err.message);
      }
    })
  );

  cache = {
    updatedAt: new Date().toISOString(),
    items: results
      .filter(item => includesAny(item.title, WATCH_TERMS))
      .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
      .slice(0, 50),
  };
}

app.get("/api/energy-news", async (req, res) => {
  if (!cache.updatedAt) {
    await refreshNews();
  }
  res.json(cache.items);
});

app.get("/api/health", (req, res) => {
  res.json({
    ok: true,
    updatedAt: cache.updatedAt,
    count: cache.items.length,
  });
});

refreshNews();
setInterval(refreshNews, 60000);

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});