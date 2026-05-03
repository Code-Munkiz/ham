import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CONTENT_STYLE_BOUNDS,
  EMOJI_VALUES,
  LENGTH_VALUES,
  TONE_VALUES,
} from "../../lib/policyConstants";
import { EMOJI_LABELS, LENGTH_LABELS, TONE_LABELS } from "../../lib/policyCopy";
import type { ContentStyle, EmojiPolicy, LengthPreference, Tone } from "../../lib/policyTypes";
import { ModeSelect } from "./ModeSelect";
import { TagInput } from "./TagInput";

export interface ContentStyleFieldsProps {
  value: ContentStyle;
  onChange: (next: ContentStyle) => void;
  disabled?: boolean;
}

export function ContentStyleFields({
  value,
  onChange,
  disabled,
}: ContentStyleFieldsProps): React.ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Content style</CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ModeSelect
          id="content_style__tone"
          label="Tone"
          value={value.tone}
          options={TONE_VALUES.map((v) => ({ value: v, label: TONE_LABELS[v] }))}
          disabled={disabled}
          onChange={(v) => onChange({ ...value, tone: v as Tone })}
        />
        <ModeSelect
          id="content_style__length"
          label="Length preference"
          value={value.length_preference}
          options={LENGTH_VALUES.map((v) => ({ value: v, label: LENGTH_LABELS[v] }))}
          disabled={disabled}
          onChange={(v) => onChange({ ...value, length_preference: v as LengthPreference })}
        />
        <ModeSelect
          id="content_style__emoji"
          label="Emoji policy"
          value={value.emoji_policy}
          options={EMOJI_VALUES.map((v) => ({ value: v, label: EMOJI_LABELS[v] }))}
          disabled={disabled}
          onChange={(v) => onChange({ ...value, emoji_policy: v as EmojiPolicy })}
        />
        <div className="md:col-span-3">
          <TagInput
            id="content_style__nature_tags"
            label="Nature tags"
            value={value.nature_tags}
            onChange={(next) => onChange({ ...value, nature_tags: next })}
            maxCount={CONTENT_STYLE_BOUNDS.nature_tags_max_count}
            disabled={disabled}
            placeholder="e.g. friendly-meta"
            helpText="Lower-case slugs (a-z, 0-9, dot, dash, underscore). Up to 8."
          />
        </div>
      </CardContent>
    </Card>
  );
}
