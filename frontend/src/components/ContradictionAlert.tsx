import React from 'react';
import { AlertTriangle } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export interface ContradictionItem {
  topic: string;
  claim_a: string;
  claim_b: string;
  sources_a?: string[];
  sources_b?: string[];
  resolution?: 'unclear' | 'A' | 'B';
  note?: string;
  company?: string;
  technology?: string;
}

interface Props {
  contradictions?: ContradictionItem[];
}

/** Amber icon + tooltip for per-finding contradiction flags (#26). */
const ContradictionAlert: React.FC<Props> = ({ contradictions }) => {
  if (!contradictions || contradictions.length === 0) return null;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 text-[10px] cursor-help">
            <AlertTriangle className="w-3.5 h-3.5" />
            {contradictions.length} conflict{contradictions.length > 1 ? 's' : ''}
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-sm text-xs space-y-2">
          {contradictions.map((c, i) => (
            <div key={i} className="border-b pb-1.5 last:border-0">
              <p className="font-medium">{c.topic}</p>
              <p className="text-muted-foreground">
                A: {c.claim_a}
              </p>
              <p className="text-muted-foreground">
                B: {c.claim_b}
              </p>
              {c.resolution && c.resolution !== 'unclear' && (
                <p>
                  Likely correct:{' '}
                  <span className="font-medium">
                    {c.resolution === 'A' ? 'Claim A' : 'Claim B'}
                  </span>
                </p>
              )}
              {c.note && (
                <p className="italic">{c.note}</p>
              )}
            </div>
          ))}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default ContradictionAlert;
