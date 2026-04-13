import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Copy, MessageSquare, ThumbsUp, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import type { SharedReportFeedback, SensingRadarItem } from '@/lib/api';
import { toast } from '@/components/ui/use-toast';

interface SensingCollaborationProps {
  shareId: string;
  radarItems: SensingRadarItem[];
}

const RINGS = ['Adopt', 'Trial', 'Assess', 'Hold'];

const RING_COLOR: Record<string, string> = {
  Adopt: 'text-emerald-600',
  Trial: 'text-blue-600',
  Assess: 'text-amber-600',
  Hold: 'text-red-600',
};

const SensingCollaboration: React.FC<SensingCollaborationProps> = ({ shareId, radarItems }) => {
  const [feedback, setFeedback] = useState<SharedReportFeedback | null>(null);
  const [loading, setLoading] = useState(true);

  // Vote form
  const [voteItem, setVoteItem] = useState('');
  const [voteRing, setVoteRing] = useState('');
  const [voteReasoning, setVoteReasoning] = useState('');
  const [submittingVote, setSubmittingVote] = useState(false);

  // Comment form
  const [commentText, setCommentText] = useState('');
  const [commentItem, setCommentItem] = useState('');
  const [submittingComment, setSubmittingComment] = useState(false);

  useEffect(() => {
    loadFeedback();
  }, [shareId]);

  const loadFeedback = async () => {
    setLoading(true);
    try {
      const data = await api.sensingGetFeedback(shareId);
      setFeedback(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const handleCopyLink = () => {
    const url = `${window.location.origin}${window.location.pathname}?shared=${shareId}`;
    navigator.clipboard.writeText(url);
    toast({ title: 'Link copied to clipboard' });
  };

  const handleVote = async () => {
    if (!voteItem || !voteRing) return;
    setSubmittingVote(true);
    try {
      await api.sensingVote(shareId, voteItem, voteRing, voteReasoning);
      toast({ title: 'Vote submitted' });
      setVoteItem('');
      setVoteRing('');
      setVoteReasoning('');
      await loadFeedback();
    } catch (err: unknown) {
      toast({ title: 'Vote failed', description: err instanceof Error ? err.message : '', variant: 'destructive' });
    } finally {
      setSubmittingVote(false);
    }
  };

  const handleComment = async () => {
    if (!commentText.trim()) return;
    setSubmittingComment(true);
    try {
      await api.sensingComment(shareId, commentText, commentItem);
      toast({ title: 'Comment added' });
      setCommentText('');
      setCommentItem('');
      await loadFeedback();
    } catch (err: unknown) {
      toast({ title: 'Comment failed', description: err instanceof Error ? err.message : '', variant: 'destructive' });
    } finally {
      setSubmittingComment(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin" /></div>;
  }

  return (
    <div className="space-y-4">
      {/* Share link */}
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={handleCopyLink}>
          <Copy className="w-4 h-4 mr-1" />
          Copy Share Link
        </Button>
        <span className="text-xs text-muted-foreground">Share ID: {shareId}</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Vote panel */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <ThumbsUp className="w-4 h-4" />
              Vote on Ring Placement
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Select value={voteItem} onValueChange={setVoteItem}>
              <SelectTrigger><SelectValue placeholder="Select technology..." /></SelectTrigger>
              <SelectContent>
                {radarItems.map(item => (
                  <SelectItem key={item.name} value={item.name}>
                    {item.name} (currently: {item.ring})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={voteRing} onValueChange={setVoteRing}>
              <SelectTrigger><SelectValue placeholder="Suggested ring..." /></SelectTrigger>
              <SelectContent>
                {RINGS.map(ring => (
                  <SelectItem key={ring} value={ring}>{ring}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              value={voteReasoning}
              onChange={(e) => setVoteReasoning(e.target.value)}
              placeholder="Reasoning (optional)"
            />
            <Button size="sm" onClick={handleVote} disabled={!voteItem || !voteRing || submittingVote}>
              {submittingVote ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Submit Vote'}
            </Button>
          </CardContent>
        </Card>

        {/* Comment panel */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <MessageSquare className="w-4 h-4" />
              Comments
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Select value={commentItem} onValueChange={setCommentItem}>
              <SelectTrigger><SelectValue placeholder="General (or pick technology)" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">General</SelectItem>
                {radarItems.map(item => (
                  <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Textarea
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder="Add a comment..."
              rows={2}
            />
            <Button size="sm" onClick={handleComment} disabled={!commentText.trim() || submittingComment}>
              {submittingComment ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Add Comment'}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Vote summary */}
      {feedback && feedback.total_votes > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Vote Summary ({feedback.total_votes} votes)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(feedback.vote_summary).map(([name, data]) => (
                <div key={name} className="flex items-center gap-2 text-sm p-2 border rounded">
                  <span className="font-medium flex-1">{name}</span>
                  <div className="flex gap-1">
                    {Object.entries(data.ring_counts).map(([ring, count]) => (
                      <Badge key={ring} variant="outline" className={`text-[10px] ${RING_COLOR[ring] || ''}`}>
                        {ring}: {count}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Comments list */}
      {feedback && feedback.comments.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">All Comments ({feedback.total_comments})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {feedback.comments.map((c) => (
                <div key={c.comment_id} className="text-sm p-2 border rounded">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium">{c.user_name}</span>
                    {c.radar_item_name && (
                      <Badge variant="secondary" className="text-[10px]">{c.radar_item_name}</Badge>
                    )}
                    <span className="text-xs text-muted-foreground ml-auto">
                      {new Date(c.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <p className="text-muted-foreground">{c.text}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default SensingCollaboration;
