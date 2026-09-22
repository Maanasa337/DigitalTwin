import { Flex, Typography } from 'antd';

/** The favicon doubles as the logo mark, so the tab, the top bar and the splash show one symbol. */
const LOGO_SRC = `${import.meta.env.BASE_URL}favicon.svg`;

export function BrandMark({ size = 24, wordmark = true }: { size?: number; wordmark?: boolean }) {
  return (
    <Flex align="center" gap={size / 3}>
      <img src={LOGO_SRC} width={size} height={size} alt="" aria-hidden style={{ display: 'block' }} />
      {wordmark && (
        <Typography.Text strong style={{ fontSize: Math.max(16, size * 0.66), letterSpacing: -0.2 }}>
          TwinVoice
        </Typography.Text>
      )}
    </Flex>
  );
}
