"""
MAAPS v4.0 - Composer Agent (Structure & Intent)

LLM-powered agent that takes SonicSignature + user prompt and generates
structured section plans with HeartMuLa-optimized prompts.

Uses Gemini 1.5/3 Pro (via Vertex or local) with strict Pydantic output schema
for sections (powers-of-2 bars, intensity, HeartMuLa-optimized prompts).

Supports fine-grained control: HeartMuLa's section-aware mode with [Verse] style tags, lyrics.
"""

import logging
from typing import Optional, List, Dict, Any
import json

from maaps_v4.schemas import SonicSignature, SectionPlan, SectionType, GenerationRequest

logger = logging.getLogger('maaps.composer')


class ComposerAgent:
    """
    Structure & Intent Agent for MAAPS v4.0
    
    Responsibilities:
    - Take SonicSignature + user prompt
    - Generate structured section plan (powers-of-2 bars)
    - Create HeartMuLa-optimized prompts for each section
    - Handle lyrics with section-aware tags
    """
    
    def __init__(self, llm_provider: str = 'gemini'):
        self.name = "ComposerAgent"
        self.llm_provider = llm_provider
        self._llm_client = None
        logger.info(f"ComposerAgent initialized with {llm_provider}")
    
    def _get_llm_client(self):
        """Lazy load LLM client"""
        if self._llm_client is None:
            if self.llm_provider == 'gemini':
                try:
                    from google import genai
                    import os
                    
                    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
                    if not api_key:
                        logger.warning("Gemini API key not found, using mock composer")
                        return None
                    
                    self._llm_client = genai.Client(api_key=api_key)
                    logger.info("Gemini LLM client initialized")
                    
                except ImportError:
                    logger.warning("google-genai not installed, using mock composer")
                    return None
            else:
                logger.warning(f"Unknown LLM provider: {self.llm_provider}, using mock")
                return None
        
        return self._llm_client
    
    async def compose(
        self,
        sonic_signature: Optional[SonicSignature],
        user_prompt: str,
        style: str,
        duration: float,
        lyrics: Optional[str] = None
    ) -> List[SectionPlan]:
        """
        Generate structured section plan
        
        Args:
            sonic_signature: Analyzed input features (optional)
            user_prompt: User creative prompt
            style: Genre/style descriptor
            duration: Target duration in seconds
            lyrics: Optional lyrics with section tags
            
        Returns:
            List of SectionPlan objects
        """
        llm = self._get_llm_client()
        
        # Estimate bar count from duration (assume ~100 BPM, 4/4 time)
        bpm = sonic_signature.bpm if sonic_signature else 100.0
        beats_per_bar = 4
        bars_per_minute = bpm / beats_per_bar
        estimated_bars = int((duration / 60.0) * bars_per_minute)
        
        # Round to nearest power of 2
        total_bars = self._nearest_power_of_two(estimated_bars)
        
        logger.info(f"Composing structure: {total_bars} bars @ {bpm} BPM, {duration:.1f}s")
        
        if llm:
            section_plans = await self._compose_with_llm(
                llm=llm,
                sonic_signature=sonic_signature,
                user_prompt=user_prompt,
                style=style,
                total_bars=total_bars,
                lyrics=lyrics
            )
        else:
            section_plans = self._compose_mock(
                sonic_signature=sonic_signature,
                user_prompt=user_prompt,
                style=style,
                total_bars=total_bars,
                lyrics=lyrics
            )
        
        return section_plans
    
    async def _compose_with_llm(
        self,
        llm,
        sonic_signature: Optional[SonicSignature],
        user_prompt: str,
        style: str,
        total_bars: int,
        lyrics: Optional[str]
    ) -> List[SectionPlan]:
        """Generate section plan using LLM"""
        
        system_prompt = """You are a music composition expert creating structured song plans for AI music generation.

Your output must be a JSON array of section objects with these fields:
- section_type: One of [intro, verse, chorus, bridge, outro, breakdown, buildup, drop]
- bar_count: Power of 2 (1, 2, 4, 8, 16, 32)
- intensity: Float 0.0-1.0 (relative energy)
- heartmula_prompt: Detailed prompt for HeartMuLa model (include instruments, mood, production style)
- style_tags: Array of genre/style descriptors
- lyrics: Optional lyrics with [Verse]/[Chorus] tags matching this section

Rules:
1. Total bars across all sections must equal exactly {{TOTAL_BARS}}
2. Each section bar_count must be a power of 2
3. Build intensity appropriately (verse < chorus, etc.)
4. HeartMuLa prompts should be specific: include BPM, key, instruments, reference artists, production techniques
5. Use section-aware tags in prompts: [Drums], [Bass], [Vocals], [Synth], etc.

Example output format:
[
  {"section_type": "intro", "bar_count": 4, "intensity": 0.3, "heartmula_prompt": "...", "style_tags": ["ambient"]},
  {"section_type": "verse", "bar_count": 8, "intensity": 0.5, "heartmula_prompt": "...", "style_tags": []},
  {"section_type": "chorus", "bar_count": 8, "intensity": 0.9, "heartmula_prompt": "...", "style_tags": ["powerful"]}
]"""
        
        context = f"""
User Prompt: {user_prompt}
Style: {style}
Total Bars: {total_bars}
"""
        
        if sonic_signature:
            context += f"""
Analyzed Input:
- BPM: {sonic_signature.bpm:.1f}
- Key: {sonic_signature.key}
- Loudness: {sonic_signature.loudness_lufs:.1f} LUFS
"""
        
        if lyrics:
            context += f"\nLyrics:\n{lyrics}"
        
        try:
            response = llm.models.generate_content(
                model="gemini-1.5-pro",
                contents=f"{system_prompt.replace('{{TOTAL_BARS}}', str(total_bars))}\n\n{context}"
            )
            
            # Parse JSON from response
            response_text = response.text.strip()
            
            # Extract JSON array (handle markdown code blocks)
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            sections_data = json.loads(response_text)
            
            # Convert to SectionPlan objects
            section_plans = []
            for section in sections_data:
                plan = SectionPlan(
                    section_type=SectionType(section['section_type']),
                    bar_count=section['bar_count'],
                    intensity=section.get('intensity', 0.5),
                    heartmula_prompt=section['heartmula_prompt'],
                    style_tags=section.get('style_tags', []),
                    lyrics=section.get('lyrics'),
                    bpm=sonic_signature.bpm if sonic_signature else None,
                    key=sonic_signature.key if sonic_signature else None
                )
                section_plans.append(plan)
            
            logger.info(f"Generated {len(section_plans)} sections via LLM")
            return section_plans
            
        except Exception as e:
            logger.error(f"LLM composition failed: {e}, falling back to mock")
            return self._compose_mock(sonic_signature, user_prompt, style, total_bars, lyrics)
    
    def _compose_mock(
        self,
        sonic_signature: Optional[SonicSignature],
        user_prompt: str,
        style: str,
        total_bars: int,
        lyrics: Optional[str]
    ) -> List[SectionPlan]:
        """Fallback mock composition when LLM unavailable"""
        
        # Simple structure: intro, verse, chorus, verse, chorus, outro
        bpm = sonic_signature.bpm if sonic_signature else 100.0
        key = sonic_signature.key if sonic_signature else "Cmajor"
        
        sections = []
        remaining_bars = total_bars
        
        # Standard pop structure allocation
        structure = [
            (SectionType.INTRO, 0.3, 4),
            (SectionType.VERSE, 0.5, 8),
            (SectionType.CHORUS, 0.8, 8),
            (SectionType.VERSE, 0.5, 8),
            (SectionType.CHORUS, 0.9, 8),
            (SectionType.OUTRO, 0.4, 4)
        ]
        
        for section_type, intensity, default_bars in structure:
            if remaining_bars <= 0:
                break
            
            bars = min(default_bars, remaining_bars)
            
            # Create HeartMuLa prompt
            prompt = self._create_heartmula_prompt(
                user_prompt=user_prompt,
                style=style,
                section_type=section_type,
                bpm=bpm,
                key=key,
                intensity=intensity
            )
            
            plan = SectionPlan(
                section_type=section_type,
                bar_count=bars,
                intensity=intensity,
                heartmula_prompt=prompt,
                style_tags=[style],
                bpm=bpm,
                key=key
            )
            
            sections.append(plan)
            remaining_bars -= bars
        
        logger.info(f"Generated {len(sections)} sections (mock mode)")
        return sections
    
    def _create_heartmula_prompt(
        self,
        user_prompt: str,
        style: str,
        section_type: SectionType,
        bpm: float,
        key: str,
        intensity: float
    ) -> str:
        """Create HeartMuLa-optimized prompt for a section"""
        
        intensity_desc = {
            0.3: "minimal, sparse arrangement",
            0.5: "moderate energy, building",
            0.8: "high energy, full arrangement",
            0.9: "maximum impact, powerful"
        }.get(intensity, "balanced")
        
        section_context = {
            SectionType.INTRO: "atmospheric introduction",
            SectionType.VERSE: "verse section with melodic development",
            SectionType.CHORUS: "catchy, memorable chorus hook",
            SectionType.BRIDGE: "contrasting bridge section",
            SectionType.OUTRO: "fading conclusion",
            SectionType.BREAKDOWN: "stripped-down breakdown",
            SectionType.BUILDUP: "tension-building rise",
            SectionType.DROP: "explosive drop"
        }.get(section_type, "main section")
        
        prompt = (
            f"{style} music, {user_prompt}. "
            f"{section_context.value.capitalize()}, {intensity_desc}. "
            f"BPM: {bpm:.0f}, Key: {key}. "
            f"[Drums] {self._drum_prompt(intensity, style)}, "
            f"[Bass] {self._bass_prompt(intensity, style)}, "
            f"[Melody] {self._melody_prompt(intensity, style)}"
        )
        
        return prompt
    
    def _drum_prompt(self, intensity: float, style: str) -> str:
        """Generate drum description"""
        if intensity < 0.4:
            return "light percussion, subtle hi-hats"
        elif intensity < 0.7:
            return "steady beat, moderate groove"
        else:
            return "powerful drums, driving rhythm, energetic fills"
    
    def _bass_prompt(self, intensity: float, style: str) -> str:
        """Generate bass description"""
        if intensity < 0.4:
            return "subtle bass foundation"
        elif intensity < 0.7:
            return "groovy bassline, supportive"
        else:
            return "aggressive bass, prominent low-end"
    
    def _melody_prompt(self, intensity: float, style: str) -> str:
        """Generate melody description"""
        if intensity < 0.4:
            return "sparse melodic elements, atmospheric"
        elif intensity < 0.7:
            return "developing melody, memorable motifs"
        else:
            return "bold lead melody, anthemic hooks"
    
    def _nearest_power_of_two(self, n: int) -> int:
        """Round to nearest power of two"""
        if n <= 1:
            return 1
        
        lower = 1 << (n.bit_length() - 1)
        upper = lower << 1
        
        if abs(n - lower) <= abs(n - upper):
            return lower
        return upper
