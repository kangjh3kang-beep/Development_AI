/* eslint-disable @typescript-eslint/no-require-imports */
const fs = require('fs');
const path = require('path');

const DASHBOARD_DIR = path.join(__dirname, 'app', '[locale]', '(dashboard)');

const parseItems = (itemsStr) => {
  if (!itemsStr) return [];
  // Match string literals inside quotes
  const regex = /"([^"]+)"/g;
  let match;
  const items = [];
  while ((match = regex.exec(itemsStr)) !== null) {
    items.push(match[1]);
  }
  return items;
};

const extractFromFiles = (dir, results) => {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const fullPath = path.join(dir, file);
    if (fs.statSync(fullPath).isDirectory()) {
      extractFromFiles(fullPath, results);
    } else if (file === 'page.tsx') {
      const content = fs.readFileSync(fullPath, 'utf8');
      
      // Look for ModulePlaceholder usage
      if (content.includes('ModulePlaceholder')) {
        // Simple regex to extract eyebrow, title, description, and items
        const titleMatch = content.match(/title="([^"]+)"/);
        
        // Exclude those already translated (Korean checks)
        if (titleMatch && /[가-힣]/.test(titleMatch[1])) {
          continue; // Already localized
        }
        
        const eyebrowMatch = content.match(/eyebrow="([^"]+)"/);
        const descMatch = content.match(/description="([^"]+)"/);
        const itemsMatch = content.match(/items=\{\[\s*([\s\S]*?)\s*\]\}/);
        
        if (titleMatch) {
          // Identify module key by folder name
          const relativePath = path.relative(DASHBOARD_DIR, dir);
          // e.g., projects/[id]/design -> design
          let moduleKey = relativePath.split(path.sep).pop();
          if (moduleKey === '[id]') moduleKey = 'project_dashboard'; // fallback
          if (moduleKey === 'analytics') moduleKey = 'analytics_base';
          if (moduleKey === 'projects') moduleKey = 'projects_base';

          // Ensure unique key
          let uniqueKey = moduleKey;
          let counter = 1;
          while (results[uniqueKey]) {
            uniqueKey = `${moduleKey}_${counter}`;
            counter++;
          }

          results[uniqueKey] = {
            eyebrow: eyebrowMatch ? eyebrowMatch[1] : "",
            title: titleMatch[1],
            description: descMatch ? descMatch[1] : "",
            items: itemsMatch ? parseItems(itemsMatch[1]) : [],
            filePath: fullPath
          };
        }
      }
    }
  }
};

const results = {};
extractFromFiles(DASHBOARD_DIR, results);

fs.writeFileSync(path.join(__dirname, 'extracted_placeholders.json'), JSON.stringify(results, null, 2));
console.log(`Extracted ${Object.keys(results).length} English placeholders. Saved to extracted_placeholders.json`);
