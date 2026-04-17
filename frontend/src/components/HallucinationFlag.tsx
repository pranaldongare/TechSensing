import React from 'react';
import { ShieldAlert } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export interface UnsupportedClaimItem {
  claim: string;
  reason: string;
  suggested_action?: 'drop' | 'flag' | 'rewrite';
  company?: string;
}

interface Props {
  unsupportedClaims?: UnsupportedClaimItem[];
}

/** Red icon + tooltip for hallucination-probe flags (#27). */
const HallucinationFlag: React.FC<Props> = ({ unsupportedClaims }) => {
  if (!unsupportedClaims || unsupportedClaims.length === 0) return null;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400 text-[10px] cursor-help">
            <ShieldAlert className="w-3.5 h-3.5" />
            {unsupportedClaims.length} unverified
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-sm text-xs space-y-2">
          {unsupportedClaims.map((c, i) => (
            <div key={i} className="border-b pb-1.5 last:border-0">
              <p className="font-medium">{c.claim}</p>
              <p className="text-muted-foreground">{c.reason}</p>
              {c.suggested_action && (
                <p>
                  Action: <span className="font-medium">{c.suggested_action}</span>
                </p>
              )}
            </div>
          ))}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default HallucinationFlag;
