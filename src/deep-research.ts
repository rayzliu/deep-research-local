import FirecrawlApp, { SearchResponse } from '@mendable/firecrawl-js';
import { generateObject } from 'ai';
import { compact } from 'lodash-es';
import pLimit from 'p-limit';
import { z } from 'zod';
import path from 'path';

import { getModel, trimPrompt } from './ai/providers';
import { systemPrompt, isChinese } from './prompt';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile as any);

function log(...args: any[]) {
  console.log(...args);
}

export type ResearchProgress = {
  currentDepth: number;
  totalDepth: number;
  currentBreadth: number;
  totalBreadth: number;
  currentQuery?: string;
  totalQueries: number;
  completedQueries: number;
};

type ResearchResult = {
  learnings: string[];
  visitedUrls: string[];
};

// increase this if you have higher API rate limits
const ConcurrencyLimit = Number(process.env.FIRECRAWL_CONCURRENCY) || 2;

// number of results to fetch from each retrieval method (set to 0 to disable)
const FIRECRAWL_SOURCES = Number(process.env.FIRECRAWL_SOURCES ?? 5);
const INTERNAL_SOURCES = Number(process.env.INTERNAL_SOURCES ?? 3);

// Initialize Firecrawl with optional API key and optional base url

const firecrawl = new FirecrawlApp({
  apiKey: process.env.FIRECRAWL_KEY ?? '',
  apiUrl: process.env.FIRECRAWL_BASE_URL,
});

// take en user query, return a list of SERP queries
async function generateSerpQueries({
  query,
  numQueries = 3,
  learnings,
}: {
  query: string;
  numQueries?: number;

  // optional, if provided, the research will continue from the last learning
  learnings?: string[];
}) {
  const promptText = isChinese()
    ? `根据用户的以下提示，为研究该主题生成一组搜索查询（SERP 查询）。最多返回 ${numQueries} 个查询，如果原始提示已足够清晰可以返回更少。确保每个查询互不相似且唯一： <prompt>${query}</prompt>\n\n${
        learnings ? `以下为先前研究的要点，使用它们生成更具体的查询： ${learnings.join('\n')}` : ''
      }`
    : `Given the following prompt from the user, generate a list of SERP queries to research the topic. Return a maximum of ${numQueries} queries, but feel free to return less if the original prompt is clear. Make sure each query is unique and not similar to each other: <prompt>${query}</prompt>\n\n${
        learnings ? `Here are some learnings from previous research, use them to generate more specific queries: ${learnings.join('\n')}` : ''
      }`;

  const res = await generateObject({
    model: getModel(),
    system: systemPrompt(),
    prompt: promptText,
    schema: z.object({
      queries: z
        .array(
          z.object({
            query: z.string().describe(
              isChinese() ? '用于搜索引擎结果页（SERP）的查询语句' : 'The SERP query'
            ),
            researchGoal: z.string().describe(
              isChinese()
                ? '首先说明该查询要完成的研究目标，然后深入说明在获得结果后如何推进研究，并提出额外的研究方向。请尽可能具体，尤其是在额外研究方向方面。'
                : 'First talk about the goal of the research that this query is meant to accomplish, then go deeper into how to advance the research once the results are found, mention additional research directions. Be as specific as possible, especially for additional research directions.'
            ),
          }),
        )
        .describe(`List of SERP queries, max of ${numQueries}`),
    }),
  });
  log(`Created ${res.object.queries.length} queries`, res.object.queries);

  return res.object.queries.slice(0, numQueries);
}


async function processSerpResult({
  query,
  contents,
  visitedUrls = [],
  numLearnings = 3,
  numFollowUpQuestions = 3,
}: {
  query: string;
  contents: string[];
  visitedUrls?: string[];
  numLearnings?: number;
  numFollowUpQuestions?: number;
}) {
  const trimmed = contents.map(c => trimPrompt(c, 25_000)).filter(Boolean);
  log(`Ran ${query}, found ${trimmed.length} contents (visitedUrls: ${visitedUrls.length})`);

  const res = await generateObject({
    model: getModel(),
    abortSignal: AbortSignal.timeout(60_000),
    system: systemPrompt(),
    prompt: trimPrompt(
      isChinese()
        ? `根据以下针对查询 <query>${query}</query> 的搜索结果内容，生成一组研究要点。最多返回 ${numLearnings} 条要点，如内容已足够清晰可返回更少。确保每条要点彼此不同且不重复。要点应简洁明了，同时尽可能信息密集且具体。务必包含任何相关实体（如人物、地点、公司、产品等），以及精确的指标、数字或日期。这些要点将用于进一步研究该主题。\n\n<contents>${trimmed
          .map(content => `<content>\n${content}\n</content>`)
          .join('\n')}</contents>`
        : `Given the following contents from a SERP search for the query <query>${query}</query>, generate a list of learnings from the contents. Return a maximum of ${numLearnings} learnings, but feel free to return less if the contents are clear. Make sure each learning is unique and not similar to each other. The learnings should be concise and to the point, as detailed and information dense as possible. Make sure to include any entities like people, places, companies, products, things, etc in the learnings, as well as any exact metrics, numbers, or dates. The learnings will be used to research the topic further.\n\n<contents>${trimmed
         .map(content => `<content>\n${content}\n</content>`)
         .join('\n')}</contents>`
    ),
    schema: z.object({
      // learnings: z.array(z.string()).describe(`List of learnings, max of ${numLearnings}`),
      // followUpQuestions: z
      //   .array(z.string())
      //   .describe(
      //     `List of follow-up questions to research the topic further, max of ${numFollowUpQuestions}`,
      //   ),
      learnings: z.array(z.string()).describe(
       isChinese()
         ? `研究要点列表，最多 ${numLearnings} 条`
         : `List of learnings, max of ${numLearnings}`
        ),
      followUpQuestions: z.array(z.string()).describe(
        isChinese()
         ? `用于进一步研究该主题的后续问题列表，最多 ${numFollowUpQuestions} 条`
         : `List of follow-up questions to research the topic further, max of ${numFollowUpQuestions}`
        ),
    }),
  });
  log(`Created ${res.object.learnings.length} learnings`, res.object.learnings);

  return res.object;
}

// Fetch hybrid results: Firecrawl + internal DB (retrieve_distilled.py)
async function fetchHybridResults(query: string, firecrawlCount: number, internalCount: number) {
  const contents: string[] = [];
  const visitedUrls: string[] = [];

  // Firecrawl
  if (firecrawlCount > 0) {
    try {
      const fcRes = await firecrawl.search(query, {
        timeout: 15000,
        limit: firecrawlCount,
        scrapeOptions: { formats: ['markdown'] },
      });
      for (const item of fcRes.data.slice(0, firecrawlCount)) {
        if (item.markdown) contents.push(item.markdown as string);
        if (item.url) visitedUrls.push(item.url as string);
      }
    } catch (e: any) {
      log('Firecrawl fetch failed for', query, e?.message ?? e);
    }
  }

  // Internal retrieval via Python distilled retriever
  if (internalCount > 0) {
    try {

      const scriptPath = path.resolve('database/retrieve_distilled.py');
      const scriptDir = path.dirname(scriptPath);
      const args = ['retrieve_distilled.py', '--q', query, '--k', String(internalCount)];
      const { stdout, stderr } = await execFileAsync(
        'python',
        args,
        { 
          cwd: scriptDir,      // ⭐ THIS IS THE FIX
          env: process.env as any 
        }
      );

      log('stdout:', stdout);
      log('stderr:', stderr);// for debugging
      const parsed = JSON.parse(stdout || '[]');
      log("parsed",parsed)
      if (Array.isArray(parsed)) {
        for (const hit of parsed.slice(0, internalCount)) {
          if (hit.distilled) contents.push(String(hit.distilled));
          if (hit.file_path) visitedUrls.push(String(hit.file_path));
        }
      }
    } catch (e: any) {
      log('Internal retrieval failed for', query, e?.message ?? e);
    }
  }

  return { contents, visitedUrls };
}

export async function writeFinalReport({
  prompt,
  learnings,
  visitedUrls,
}: {
  prompt: string;
  learnings: string[];
  visitedUrls: string[];
}) {
  const learningsString = learnings
    .map(learning => `<learning>\n${learning}\n</learning>`)
    .join('\n');

  const res = await generateObject({
    model: getModel(),
    system: systemPrompt(),
    prompt: trimPrompt(
      isChinese()
        ? `根据用户以下提示并使用研究所得要点，撰写最终报告。尽量详尽，目标为三页或以上，包含所有研究要点：\n\n<prompt>${prompt}</prompt>\n\n以下为所有要点：\n\n<learnings>\n${learningsString}\n</learnings>`
        : `Given the following prompt from the user, write a final report on the topic using the learnings from research. Make it as as detailed as possible, aim for 3 or more pages, include ALL the learnings from research:\n\n<prompt>${prompt}</prompt>\n\nHere are all the learnings from previous research:\n\n<learnings>\n${learningsString}\n</learnings>`,
    ),
    schema: z.object({
      reportMarkdown: z.string().describe(
        isChinese()
          ? '以 Markdown 格式撰写的主题最终报告'
          : 'Final report on the topic in Markdown'
        ),
    }),
  });

  // Append the visited URLs section to the report
  const urlsSection = `\n\n## Sources\n\n${visitedUrls.map(url => `- ${url}`).join('\n')}`;
  return res.object.reportMarkdown + urlsSection;
}

export async function writeFinalAnswer({
  prompt,
  learnings,
}: {
  prompt: string;
  learnings: string[];
}) {
  const learningsString = learnings
    .map(learning => `<learning>\n${learning}\n</learning>`)
    .join('\n');

  const res = await generateObject({
    model: getModel(),
    system: systemPrompt(),
    prompt: trimPrompt(
        isChinese()
          ? `根据用户以下提示并使用研究所得要点，撰写最终答案。严格遵循提示的格式，只返回答案本身，不要额外文字。尽量简洁（通常几词或最多一句）。如果提示使用 LaTeX，则以 LaTeX 格式回答；如果提示包含多选项，请返回其中一个选项。\n\n<prompt>${prompt}</prompt>\n\n以下为研究要点：\n\n<learnings>\n${learningsString}\n</learnings>`
          : `Given the following prompt from the user, write a final answer on the topic using the learnings from research. Follow the format specified in the prompt. Do not include any extra text beyond the answer itself. Keep the answer as concise as possible - usually it should be just a few words or at most a sentence. If the prompt is using LaTeX, answer in LaTeX. If the prompt gives multiple answer choices, return one of the choices.\n\n<prompt>${prompt}</prompt>\n\nHere are all the learnings from research on the topic that you can use to help answer the prompt:\n\n<learnings>\n${learningsString}\n</learnings>`,
    ),
    schema: z.object({
      // exactAnswer: z
      //   .string()
      //   .describe('The final answer, make it short and concise, just the answer, no other text'),
      exactAnswer: z.string().describe(
        isChinese()
          ? '最终答案，应尽量简短，仅返回答案本身，不包含其他文字'
          : 'The final answer, make it short and concise, just the answer, no other text'
        ),
    }),
  });

  return res.object.exactAnswer;
}

// deepResearch: recursively run queries and process results
export async function deepResearch({
  query,
  breadth,
  depth,
  learnings = [],
  visitedUrls = [],
  onProgress,
}: {
  query: string;
  breadth: number;
  depth: number;
  learnings?: string[];
  visitedUrls?: string[];
  onProgress?: (progress: ResearchProgress) => void;
}): Promise<ResearchResult> {
  const progress: ResearchProgress = {
    currentDepth: depth,
    totalDepth: depth,
    currentBreadth: breadth,
    totalBreadth: breadth,
    totalQueries: 0,
    completedQueries: 0,
  };

  const reportProgress = (update: Partial<ResearchProgress>) => {
    Object.assign(progress, update);
    onProgress?.(progress);
  };

  const serpQueries = await generateSerpQueries({
    query,
    learnings,
    numQueries: breadth,
  });

  reportProgress({
    totalQueries: serpQueries.length,
    currentQuery: serpQueries[0]?.query,
  });

  const limit = pLimit(ConcurrencyLimit);

  const results = await Promise.all(
    serpQueries.map(serpQuery =>
      limit(async () => {
        try {
          const { contents: fetchedContents, visitedUrls: newUrls } = await fetchHybridResults(
            serpQuery.query,
            FIRECRAWL_SOURCES,
            INTERNAL_SOURCES,
          );

          const newBreadth = Math.ceil(breadth / 2);
          const newDepth = depth - 1;

          const newLearnings = await processSerpResult({
            query: serpQuery.query,
            contents: fetchedContents,
            visitedUrls: newUrls,
            numFollowUpQuestions: newBreadth,
          });
          const allLearnings = [...learnings, ...newLearnings.learnings];
          const allUrls = [...visitedUrls, ...newUrls];

          if (newDepth > 0) {
            log(`Researching deeper, breadth: ${newBreadth}, depth: ${newDepth}`);

            reportProgress({
              currentDepth: newDepth,
              currentBreadth: newBreadth,
              completedQueries: progress.completedQueries + 1,
              currentQuery: serpQuery.query,
            });

            const nextQuery = `
            Previous research goal: ${serpQuery.researchGoal}
            Follow-up research directions: ${newLearnings.followUpQuestions.map(q => `\n${q}`).join('')}
          `.trim();

            return deepResearch({
              query: nextQuery,
              breadth: newBreadth,
              depth: newDepth,
              learnings: allLearnings,
              visitedUrls: allUrls,
              onProgress,
            });
          } else {
            reportProgress({
              currentDepth: 0,
              completedQueries: progress.completedQueries + 1,
              currentQuery: serpQuery.query,
            });
            return {
              learnings: allLearnings,
              visitedUrls: allUrls,
            };
          }
        } catch (e: any) {
          if (e.message && e.message.includes('Timeout')) {
            log(`Timeout error running query: ${serpQuery.query}: `, e);
          } else {
            log(`Error running query: ${serpQuery.query}: `, e);
          }
          return {
            learnings: [],
            visitedUrls: [],
          };
        }
      }),
    ),
  );

  return {
    learnings: [...new Set(results.flatMap(r => r.learnings))],
    visitedUrls: [...new Set(results.flatMap(r => r.visitedUrls))],
  };
}
