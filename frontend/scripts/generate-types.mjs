import fs from "node:fs/promises";
import path from "node:path";

import openapiTS, { astToString } from "openapi-typescript";

const schemaUrl = process.env.OPENAPI_URL ?? "http://localhost:8000/openapi.json";
const outputPath = path.resolve(process.cwd(), "src/api/types.ts");

const ast = await openapiTS(schemaUrl, {
  alphabetize: true,
});

await fs.writeFile(outputPath, astToString(ast), "utf8");
console.log(`Generated ${outputPath} from ${schemaUrl}`);
