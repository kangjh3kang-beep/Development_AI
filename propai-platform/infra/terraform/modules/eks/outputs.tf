# PropAI v30.0 - EKS 모듈 출력
output "cluster_name" {
  description = "EKS 클러스터 이름"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "EKS API 엔드포인트"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_ca_certificate" {
  description = "클러스터 CA 인증서 (base64)"
  value       = aws_eks_cluster.main.certificate_authority[0].data
}

output "node_security_group_id" {
  description = "노드 보안 그룹 ID"
  value       = aws_security_group.node.id
}

output "oidc_provider_arn" {
  description = "OIDC 프로바이더 ARN"
  value       = aws_iam_openid_connect_provider.eks.arn
}
